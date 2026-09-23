import pandas as pd
import streamlit as st

from services.database import count_related_articles, initialise_database, list_articles, save_articles
from services.news_feed import fetch_google_news
from services.predictor import screen_article

st.set_page_config(page_title="News Credibility Screening", page_icon="📰", layout="wide")
initialise_database()

st.title("News Credibility Screening Dashboard")
st.caption("A decision-support tool. It flags linguistic patterns and source context; it does not prove an article true or false.")

ingest_tab, library_tab, screen_tab, about_tab = st.tabs(["Get news", "News library", "Screen article", "About"])

with ingest_tab:
    st.subheader("Import current Google News results")
    with st.form("ingest_news"):
        query = st.text_input("Topic or search phrase", placeholder="Enter topic you want to search for")
        number = st.slider("Articles to fetch", 5, 1000, 100)
        submitted = st.form_submit_button("Fetch and save news")
    if submitted:
        try:
            with st.spinner("Fetching the RSS feed…"):
                articles = fetch_google_news(query, number)
                inserted = save_articles(articles)
            if not articles:
                st.info("No stories were returned for this search. Try a broader topic or try again shortly.")
            else:
                st.success(f"Fetched {len(articles)} articles; saved {inserted} new records.")
                st.dataframe(pd.DataFrame(articles)[["title", "source", "published_at", "url"]], hide_index=True, width="stretch")
        except (ValueError, RuntimeError) as error:
            st.error(str(error))

with library_tab:
    st.subheader("Stored news")
    articles = list_articles()
    if articles:
        table = pd.DataFrame(articles)
        st.dataframe(table[["title", "source", "published_at", "search_query", "url"]], hide_index=True, width="stretch")
    else:
        st.info("No articles saved yet. Use Get news to import a topic.")

with screen_tab:
    st.subheader("Screen an article")
    title = st.text_input("Headline", key="screen_title")
    text = st.text_area("Article text or summary", key="screen_text", height=180)
    if st.button("Run credibility screening", type="primary"):
        if not title and not text:
            st.warning("Enter a headline or article text.")
        else:
            try:
                label, confidence = screen_article(title, text)
                related = count_related_articles(title)
                first, second = st.columns(2)
                first.metric("Screening result", label)
                second.metric("Model confidence", f"{confidence:.1f}%")
                st.caption(f"Related records in your local library: {related}. Model confidence is not factual certainty.")
            except (FileNotFoundError, OSError, ValueError, RuntimeError) as error:
                st.warning("The model has not been trained yet, or the saved model is invalid. Google News records can still be collected and stored.")
                st.code("py prepare_welfake.py path\\to\\WELFake_Dataset.csv\npy train_model.py data\\welfake_prepared.csv --epochs 1")
                if st.session_state.get("debug_model_error"):
                    st.caption(str(error))

with about_tab:
    st.markdown("""
### What this project does
It collects current Google News RSS metadata, stores it locally, and lets a trained text classifier screen articles.

### Responsible use
The classifier may inherit errors and bias from its training data. Always open the publisher link, compare independent reporting, and use professional fact-checking sources for consequential claims.
""")
