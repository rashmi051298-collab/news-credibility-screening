"""Google News RSS ingestion. It intentionally stores feed metadata, not scraped articles."""
from __future__ import annotations

from urllib.parse import quote_plus

import feedparser


def google_news_rss_url(query: str, country: str = "IN", language: str = "en") -> str:
    encoded_query = quote_plus(query.strip())
    return (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl={language}-{country}&gl={country}&ceid={country}:{language}"
    )


def fetch_google_news(query: str, limit: int = 25) -> list[dict[str, str]]:
    if not query.strip():
        raise ValueError("Enter a topic or search phrase.")

    feed = feedparser.parse(google_news_rss_url(query))
    if getattr(feed, "bozo", False) and not getattr(feed, "entries", None):
        raise RuntimeError("Google News could not be reached. Try again shortly.")

    entries = getattr(feed, "entries", [])
    if not entries:
        return []

    articles: list[dict[str, str]] = []
    for entry in entries[:limit]:
        source = getattr(entry, "source", {})
        source_name = source.get("title", "Unknown source") if source else "Unknown source"
        article = {
            "title": entry.get("title", "Untitled"),
            "summary": entry.get("summary", ""),
            "source": source_name,
            "url": entry.get("link", ""),
            "published_at": entry.get("published", ""),
            "search_query": query.strip(),
        }
        if article["url"]:
            articles.append(article)
    return articles
