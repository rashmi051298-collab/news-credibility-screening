"""Google News RSS ingestion. It intentionally stores feed metadata, not scraped articles."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

import feedparser

from services.credibility import (
    RECOGNIZED_NEWSROOMS,
    article_matches_topic,
    trusted_source_name,
)

TRENDING_REGIONS = {
    "India": {
        "country": "IN",
        "sectors": [
            ("National affairs", "NATION"),
            ("Business", "BUSINESS"),
            ("Technology", "TECHNOLOGY"),
            ("Science", "SCIENCE"),
            ("Health", "HEALTH"),
            ("Sports", "SPORTS"),
            ("Entertainment", "ENTERTAINMENT"),
        ],
    },
    "World": {
        "country": "US",
        "sectors": [
            ("World affairs", "WORLD"),
            ("Business", "BUSINESS"),
            ("Technology", "TECHNOLOGY"),
            ("Science", "SCIENCE"),
            ("Health", "HEALTH"),
            ("Sports", "SPORTS"),
            ("Entertainment", "ENTERTAINMENT"),
        ],
    },
}


def google_news_rss_url(query: str, country: str = "IN", language: str = "en") -> str:
    encoded_query = quote_plus(query.strip())
    return (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl={language}-{country}&gl={country}&ceid={country}:{language}"
    )


def google_news_topic_rss_url(topic: str, country: str, language: str = "en") -> str:
    params = urlencode(
        {
            "hl": f"{language}-{country}",
            "gl": country,
            "ceid": f"{country}:{language}",
        }
    )
    return f"https://news.google.com/rss/headlines/section/topic/{topic}?{params}"


def _parse_remote_feed(url: str) -> Any:
    request = Request(
        url,
        headers={"Accept": "application/rss+xml, application/xml", "User-Agent": "NewsCredibilityScreening/1.0"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            feed = feedparser.parse(response.read())
    except OSError as error:
        raise RuntimeError("Could not retrieve a Google News topic feed.") from error
    if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
        raise RuntimeError("Google News returned an unreadable topic feed.")
    return feed


def _fetch_trending_sector(
    region: str,
    country: str,
    sector: str,
    topic: str,
) -> tuple[str, str, list[dict[str, str]]]:
    feed = _parse_remote_feed(google_news_topic_rss_url(topic, country))
    articles = []
    for entry in getattr(feed, "entries", []):
        source = entry.get("source", {})
        source_name = source.get("title", "Unknown source") if source else "Unknown source"
        source_url = source.get("href", "") if source else ""
        if not trusted_source_name(source_url):
            continue
        url = entry.get("link", "")
        if not url:
            continue
        articles.append(
            {
                "title": entry.get("title", "Untitled"),
                "summary": entry.get("summary", ""),
                "source": source_name,
                "source_url": source_url,
                "url": url,
                "published_at": entry.get("published", ""),
                "region": region,
                "sector": sector,
            }
        )
    return region, sector, articles


def fetch_trending_news(limit: int = 10) -> tuple[list[dict[str, str]], list[str]]:
    """Fetch a live, source-filtered and sector-diverse selection of Google News headlines."""
    if limit < 1:
        raise ValueError("Trending article limit must be at least 1.")

    feeds = [
        (region, details["country"], sector, topic)
        for region, details in TRENDING_REGIONS.items()
        for sector, topic in details["sectors"]
    ]
    results: dict[tuple[str, str], list[dict[str, str]]] = {}
    errors = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_trending_sector, region, country, sector, topic): (
                region,
                sector,
            )
            for region, country, sector, topic in feeds
        }
        for future in as_completed(futures):
            region, sector = futures[future]
            try:
                result_region, result_sector, articles = future.result()
            except RuntimeError as error:
                errors.append(f"{region} / {sector}: {error}")
                continue
            results[(result_region, result_sector)] = articles

    if not results and errors:
        raise RuntimeError("Could not load any live Google News topic feeds.")

    all_candidates = [
        article
        for region, details in TRENDING_REGIONS.items()
        for sector, _ in details["sectors"]
        for article in results.get((region, sector), [])
    ]
    selected: list[dict[str, str]] = []
    seen = set()
    region_counts = {region: 0 for region in TRENDING_REGIONS}
    sector_counts = {}

    def add_candidate(article: dict[str, str]) -> bool:
        identity = article["url"] or article["title"].casefold()
        if identity in seen:
            return False
        seen.add(identity)
        selected.append(article)
        region_counts[article["region"]] += 1
        sector_counts[article["sector"]] = sector_counts.get(article["sector"], 0) + 1
        return True

    sector_order = list(
        dict.fromkeys(
            sector
            for details in TRENDING_REGIONS.values()
            for sector, _ in details["sectors"]
        )
    )
    for sector in sector_order:
        candidates = [
            article for article in all_candidates if article["sector"] == sector
        ]
        candidates.sort(key=lambda article: region_counts[article["region"]])
        for article in candidates:
            if add_candidate(article):
                break

    while len(selected) < limit:
        candidates = [
            article
            for article in all_candidates
            if article["url"] not in seen
        ]
        if not candidates:
            break
        candidates.sort(
            key=lambda article: (
                region_counts[article["region"]],
                sector_counts.get(article["sector"], 0),
            )
        )
        add_candidate(candidates[0])

    return selected[:limit], sorted(errors)


def fetch_google_news(
    query: str,
    limit: int = 25,
    recognized_sources_only: bool = True,
) -> list[dict[str, str]]:
    if not query.strip():
        raise ValueError("Enter a topic or search phrase.")
    if limit < 1:
        raise ValueError("Article limit must be at least 1.")

    search_query = query.strip()
    if recognized_sources_only:
        source_sites = " OR ".join(f"site:{domain}" for domain in RECOGNIZED_NEWSROOMS)
        search_query = f"{search_query} ({source_sites})"

    feed = feedparser.parse(google_news_rss_url(search_query))
    if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
        raise RuntimeError("Google News could not be reached. Try again shortly.")

    entries = getattr(feed, "entries", [])
    if not entries:
        return []

    articles: list[dict[str, str]] = []
    for entry in entries:
        source = getattr(entry, "source", {})
        source_name = source.get("title", "Unknown source") if source else "Unknown source"
        source_url = source.get("href", "") if source else ""
        if recognized_sources_only and not trusted_source_name(source_url):
            continue
        article = {
            "title": entry.get("title", "Untitled"),
            "summary": entry.get("summary", ""),
            "source": source_name,
            "source_url": source_url,
            "url": entry.get("link", ""),
            "published_at": entry.get("published", ""),
            "search_query": query.strip(),
        }
        if article["url"] and article_matches_topic(article, query):
            articles.append(article)
        if len(articles) >= limit:
            break
    return articles
