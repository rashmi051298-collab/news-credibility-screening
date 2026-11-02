import os

import pandas as pd
import streamlit as st

from services.database import (
    group_articles_by_saved_month,
    initialise_database,
    list_articles,
    save_articles,
    update_article_credibility,
    update_article_fact_check,
    update_article_tone,
)
from services.credibility import (
    assess_coverage,
    assess_headline_coverage,
    assess_saved_story_sources,
    estimate_article_tone,
    filter_recognized_sources,
    filter_saved_articles_by_topic,
    format_fact_check_status,
)
from services.fact_check import (
    describe_fact_check_status,
    search_fact_checks,
    unverified_result,
)
from services.news_feed import fetch_google_news, fetch_trending_news

st.set_page_config(page_title="News Credibility Screening", page_icon="📰", layout="wide")
initialise_database()


def clear_search_field(key: str) -> None:
    st.session_state[key] = ""


st.title("News Credibility Screening Dashboard")
st.caption(
    "Collects live headlines and checks them against published fact-check reviews. "
    "Missing fact-check reviews are reported explicitly, not treated as a verdict."
)

ingest_tab, library_tab, screen_tab, about_tab = st.tabs(
    ["Get news", "News library", "Fact-check a claim", "About"]
)

with ingest_tab:
    st.subheader("Top 10 live trending news — India & World")
    st.caption(
        "Loads current Google News topic feeds across national affairs, world affairs, business, "
        "technology, science, health, sports, and entertainment. Headlines are drawn from "
        "recognized publishers; VERIFIED confirms the source domain, not the claims."
    )
    refresh_trending = st.button("Refresh trending news", key="refresh_trending_news")
    if "trending_news" not in st.session_state or refresh_trending:
        try:
            with st.spinner("Loading live India and world headlines across sectors…"):
                trending_articles, trending_errors = fetch_trending_news(limit=10)
                st.session_state["trending_news"] = assess_coverage(trending_articles)
                st.session_state["trending_news_errors"] = trending_errors
                st.session_state["trending_news_updated_at"] = (
                    pd.Timestamp.now(tz="Asia/Kolkata").strftime("%d %b %Y, %I:%M:%S %p IST")
                )
                st.session_state["trending_news_error"] = ""
        except (OSError, RuntimeError, ValueError) as error:
            st.session_state["trending_news"] = []
            st.session_state["trending_news_errors"] = []
            st.session_state["trending_news_error"] = str(error)

    if st.session_state.get("trending_news_error"):
        st.error(f"Could not load live trending news: {st.session_state['trending_news_error']}")
    else:
        trending_articles = st.session_state.get("trending_news", [])
        if trending_articles:
            st.caption(
                f"Last refreshed: {st.session_state['trending_news_updated_at']} · "
                f"{len(trending_articles)} headlines"
            )
            if st.session_state.get("trending_news_errors"):
                st.warning(
                    "Some topic feeds could not be loaded: "
                    + "; ".join(st.session_state["trending_news_errors"])
                )
            trending_table = pd.DataFrame(
                [
                    {"rank": index, **article}
                    for index, article in enumerate(trending_articles, start=1)
                ]
            )
            st.dataframe(
                trending_table[
                    [
                        "rank",
                        "region",
                        "sector",
                        "title",
                        "source",
                        "source_verification",
                        "published_at",
                        "url",
                    ]
                ],
                column_config={
                    "rank": st.column_config.NumberColumn("Rank", format="%d"),
                    "region": st.column_config.TextColumn("Coverage"),
                    "sector": st.column_config.TextColumn("Sector"),
                    "source_verification": st.column_config.TextColumn("Source verification"),
                    "url": st.column_config.LinkColumn("Article URL"),
                },
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No current headlines from recognized publishers were returned. Refresh to try again.")

    st.divider()
    st.subheader("Import current Google News results")
    api_key = os.getenv("GOOGLE_FACT_CHECK_API_KEY", "").strip()
    if not api_key:
        st.info(
            "Google News headlines can be collected without an API key. The table will show "
            "VERIFIED for recognized sources; set GOOGLE_FACT_CHECK_API_KEY to look up published "
            "claim reviews."
        )
    st.caption(
        "Choose recognized newsrooms only or all Google News results. VERIFIED confirms a "
        "publisher domain is on the recognized-newsroom list, not the truth of the headline."
    )
    with st.form("ingest_news", enter_to_submit=True):
        query = st.text_input(
            "Topic or search phrase",
            placeholder="Enter topic you want to search for",
            key="ingest_query",
        )
        number = st.slider("Articles to fetch", 5, 25, 10)
        source_mode = st.selectbox(
            "Publishers",
            ["Recognized newsrooms only", "All Google News results"],
        )
        submitted = st.form_submit_button("Fetch and save news")
    st.button(
        "Refresh search",
        key="refresh_ingest_search",
        on_click=clear_search_field,
        args=("ingest_query",),
        help="Clear the search phrase and hide the current search results. Saved articles remain in the library.",
    )
    if submitted:
        recognized_sources_only = source_mode == "Recognized newsrooms only"
        try:
            with st.spinner("Fetching live headlines and checking published reviews…"):
                articles = fetch_google_news(
                    query,
                    number,
                    recognized_sources_only=recognized_sources_only,
                )
                articles = assess_coverage(articles)
                if recognized_sources_only:
                    articles = filter_recognized_sources(articles)
                articles = assess_saved_story_sources(articles)
                for article in articles:
                    article["article_tone"] = estimate_article_tone(
                        f"{article.get('title', '')} {article.get('summary', '')}"
                    )
                inserted = save_articles(articles)
                fact_check_errors = []
                for article in articles:
                    article.update(unverified_result())
                    if api_key:
                        try:
                            article.update(search_fact_checks(article["title"], api_key))
                        except RuntimeError as error:
                            fact_check_errors.append(f"{article['title']}: {error}")
                    update_article_credibility(article)
                    update_article_tone(article)
                    update_article_fact_check(article)

            if not articles:
                if recognized_sources_only:
                    st.info(
                        "No headlines from recognized publisher domains were returned. "
                        "Try a broader topic or try again shortly."
                    )
                else:
                    st.info("No Google News results were returned. Try a broader topic or try again shortly.")
            else:
                st.success(
                    f"Fetched {len(articles)} headlines from "
                    f"{'recognized publishers' if recognized_sources_only else 'Google News'}; "
                    f"saved {inserted} new records."
                )
                st.caption(
                    "Source verification confirms the publisher domain only. Claim fact-check "
                    "ratings come separately from linked published reviews. Article tone is a "
                    "wording-based estimate from the headline and summary, not public sentiment."
                )
                if fact_check_errors:
                    st.error(
                        "Some claim fact-check lookups failed. No claim verdict is shown for those headlines."
                    )
                    for error in fact_check_errors:
                        st.caption(error)
                news_table = pd.DataFrame(articles)
                news_table["fact_check_status"] = [
                    format_fact_check_status(source_url, claim_status)
                    for source_url, claim_status in zip(
                        news_table["source_url"],
                        news_table["fact_check_status"],
                    )
                ]
                st.dataframe(
                    news_table[
                        [
                            "title",
                            "source",
                            "published_at",
                            "source_verification",
                            "recognized_source",
                            "first_reported_by",
                            "coverage_signal",
                            "corroborating_outlets",
                            "article_tone",
                            "fact_check_status",
                            "fact_check_rating",
                            "fact_check_publisher",
                            "fact_check_url",
                            "url",
                        ]
                    ],
                    column_config={
                        "source_verification": st.column_config.TextColumn("Source verification"),
                        "recognized_source": st.column_config.TextColumn("Recognized publisher"),
                        "first_reported_by": st.column_config.TextColumn("First reported by"),
                        "coverage_signal": st.column_config.TextColumn("Credibility signal"),
                        "corroborating_outlets": st.column_config.TextColumn("Other recognized outlets"),
                        "article_tone": st.column_config.TextColumn("Article tone estimate"),
                        "fact_check_status": st.column_config.TextColumn("Source / claim status"),
                        "fact_check_url": st.column_config.LinkColumn("Fact-check review"),
                        "url": st.column_config.LinkColumn("Article URL"),
                    },
                    hide_index=True,
                    width="stretch",
                )
        except (ValueError, RuntimeError) as error:
            st.error(str(error))

with library_tab:
    st.subheader("News library")
    st.button("Refresh library", key="refresh_news_library")
    st.caption(
        "Saved articles are grouped by the month they entered the library, using IST. "
        "Articles with a recorded search topic are shown only when their title or summary "
        "matches it. Older entries without a recorded topic remain visible. Article tone is a "
        "wording estimate, not public sentiment or a fact-check rating."
    )
    articles = filter_saved_articles_by_topic(list_articles())
    articles = assess_saved_story_sources(articles)
    for article in articles:
        if article.get("article_tone") in {None, "", "Not assessed"}:
            article["article_tone"] = estimate_article_tone(
                f"{article.get('title', '')} {article.get('summary', '')}"
            )
            update_article_tone(article)
    if articles:
        for saved_month, saved_articles in group_articles_by_saved_month(articles):
            st.markdown(f"#### {saved_month}")
            table = pd.DataFrame(saved_articles)
            table["fact_check_status"] = [
                format_fact_check_status(source_url, claim_status)
                for source_url, claim_status in zip(
                    table["source_url"],
                    table["fact_check_status"],
                )
            ]
            st.dataframe(
                table[
                    [
                        "saved_at_ist",
                        "title",
                        "source",
                        "published_at",
                        "search_query",
                        "recognized_source",
                        "first_reported_by",
                        "coverage_signal",
                        "corroborating_outlets",
                        "article_tone",
                        "fact_check_status",
                        "fact_check_rating",
                        "fact_check_publisher",
                        "fact_check_url",
                        "url",
                    ]
                ],
                column_config={
                    "saved_at_ist": st.column_config.TextColumn("Saved at (IST)"),
                    "recognized_source": st.column_config.TextColumn("Recognized publisher"),
                    "first_reported_by": st.column_config.TextColumn("First reported by"),
                    "coverage_signal": st.column_config.TextColumn("Credibility signal"),
                    "corroborating_outlets": st.column_config.TextColumn("Other recognized outlets"),
                    "article_tone": st.column_config.TextColumn("Article tone estimate"),
                    "fact_check_status": st.column_config.TextColumn("Source / claim status"),
                    "fact_check_url": st.column_config.LinkColumn("Fact-check review"),
                    "url": st.column_config.LinkColumn("Article URL"),
                },
                hide_index=True,
                width="stretch",
            )
    else:
        st.info("No articles saved yet. Use Get news to import a topic.")

with screen_tab:
    st.subheader("Assess a headline against current reporting and fact checks")
    st.caption(
        "Each headline gets a source-coverage check. A factual/fake verdict is only shown when a "
        "published fact-check review supports it."
    )
    api_key = os.getenv("GOOGLE_FACT_CHECK_API_KEY", "").strip()
    with st.form("screen_headline", enter_to_submit=True):
        title = st.text_input("Headline", key="screen_title")
        submitted = st.form_submit_button("Check this headline", type="primary")
    st.button(
        "Refresh search",
        key="refresh_headline_search",
        on_click=clear_search_field,
        args=("screen_title",),
        help="Clear the headline and hide the current check results. Saved articles remain in the library.",
    )
    if submitted:
        if not title.strip():
            st.warning("Enter an article headline to check.")
        else:
            coverage_result = None
            coverage_error = ""
            fact_check_result = unverified_result()
            fact_check_error = ""

            try:
                with st.spinner("Checking current reports from recognized newsrooms…"):
                    current_reports = fetch_google_news(title.strip(), limit=25)
                    current_reports = assess_coverage(current_reports)
                    coverage_result = assess_headline_coverage(title.strip(), current_reports)
            except (OSError, ValueError, RuntimeError) as error:
                coverage_error = str(error)

            if api_key:
                try:
                    with st.spinner("Searching published fact-check reviews…"):
                        fact_check_result = search_fact_checks(title, api_key)
                except (OSError, ValueError, RuntimeError) as error:
                    fact_check_error = str(error)
            else:
                fact_check_error = (
                    "Fact-check lookup is unavailable until GOOGLE_FACT_CHECK_API_KEY is configured."
                )

            st.subheader("Current reporting")
            if coverage_error:
                st.error(f"Could not check current news reports: {coverage_error}")
            elif coverage_result:
                st.info(f"**{coverage_result['coverage_status']}**")
                if coverage_result["coverage_sources"]:
                    st.success(
                        "Matching coverage found in "
                        f"**{coverage_result['coverage_source_count']} recognized "
                        "publisher(s)**"
                    )
                    st.write(f"Recognized publishers: {coverage_result['coverage_sources']}")
                    st.caption(
                        "This reflects matching reports returned by Google News from the "
                        "dashboard's curated publisher list. It is not an exhaustive search "
                        "of every newspaper or news channel, and coverage does not prove a claim true."
                    )
                if coverage_result["matching_articles"]:
                    st.dataframe(
                        pd.DataFrame(coverage_result["matching_articles"])[
                            ["title", "recognized_source", "published_at", "url"]
                        ],
                        column_config={
                            "url": st.column_config.LinkColumn("Article URL"),
                        },
                        hide_index=True,
                        width="stretch",
                    )
                elif current_reports:
                    st.caption(
                        "These reports discuss related topics but did not meet the headline-match "
                        "threshold, so they are not counted as confirmation."
                    )
                    st.dataframe(
                        pd.DataFrame(current_reports)[
                            ["title", "recognized_source", "published_at", "url"]
                        ],
                        column_config={
                            "url": st.column_config.LinkColumn("Article URL"),
                        },
                        hide_index=True,
                        width="stretch",
                    )
                else:
                    st.caption("No current reports from the recognized-newsroom list were returned.")

            st.subheader("Published fact-check")
            status = fact_check_result["fact_check_status"]
            status_description = describe_fact_check_status(
                fact_check_result,
                fact_check_error,
            )
            if status.startswith("Fake"):
                st.error(f"**{status_description}**")
            elif status.startswith("Factual"):
                st.success(f"**{status_description}**")
            elif status == "Mixed / unclear":
                st.warning(f"**{status_description}**")
            else:
                st.info(f"**{status_description}**")
            if fact_check_error:
                st.caption(fact_check_error)
            if fact_check_result["fact_check_claim"]:
                st.write(f"**Reviewed claim:** {fact_check_result['fact_check_claim']}")
            if fact_check_result["fact_check_rating"]:
                st.write(f"**Publisher rating:** {fact_check_result['fact_check_rating']}")
            if fact_check_result["fact_check_publisher"]:
                st.write(f"**Fact-check publisher:** {fact_check_result['fact_check_publisher']}")
            if fact_check_result["fact_check_url"]:
                st.link_button("Open fact-check review", fact_check_result["fact_check_url"])
            st.caption(
                "Source verification confirms publisher identity, not that a claim is true. "
                "A factual/fake rating requires a matching published fact-check review."
            )

with about_tab:
    st.markdown("""
### What this project does
Get news can collect headlines only from curated recognized publisher domains or from all Google News results. Recognized domains are marked as VERIFIED; this confirms publisher identity, not claim accuracy. It separately compares similar headlines across different outlets and checks claims against published reviews from Google's Fact Check Tools API.

### Responsible use
Source verification confirms a publisher domain, not the truth of the headline. A factual/fake label requires a linked published review of the matching claim. When no matching review is found, the dashboard says so instead of displaying an “Unverified” claim verdict. A claim-level review may not cover an entire article; open the cited review and original article before drawing conclusions.
""")
