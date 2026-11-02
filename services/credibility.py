"""Transparent outlet and independent-coverage signals for current headlines."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from typing import Any


RECOGNIZED_NEWSROOMS = {
    "apnews.com": "Associated Press",
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "dw.com": "Deutsche Welle",
    "france24.com": "France 24",
    "indianexpress.com": "The Indian Express",
    "ndtv.com": "NDTV",
    "reuters.com": "Reuters",
    "theguardian.com": "The Guardian",
    "thehindu.com": "The Hindu",
    "timesofindia.indiatimes.com": "The Times of India",
    "aljazeera.com": "Al Jazeera",
    "npr.org": "NPR",
    "pbs.org": "PBS",
    "ptinews.com": "Press Trust of India",
    "abc.net.au": "ABC Australia",
}

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the",
    "their", "this", "to", "was", "were", "will", "with",
}
_TOPIC_STOP_WORDS = {
    "about", "current", "happening", "latest", "news", "today", "update", "updates",
}
_NEGATION_TERMS = {"no", "not", "never"}
_TONE_NEGATIONS = {"no", "not", "never", "without"}
_POSITIVE_TONE_TERMS = {
    "achievement", "approved", "benefit", "breakthrough", "celebrate", "gain",
    "gains", "good", "growth", "hope", "improve", "improved", "improves",
    "improving", "positive", "progress", "success", "successful", "win", "wins",
}
_NEGATIVE_TONE_TERMS = {
    "attack", "crash", "crisis", "death", "decline", "disaster", "fail", "fails",
    "failed", "fear", "killed", "loss", "losses", "negative", "risk", "scandal",
    "strike", "threat", "violence", "war",
}


def trusted_source_name(source_url: str) -> str:
    """Return a recognized newsroom name only when its publisher domain matches."""
    host = (urlsplit(source_url).hostname or "").casefold().rstrip(".")
    for domain, name in RECOGNIZED_NEWSROOMS.items():
        if host == domain or host.endswith(f".{domain}"):
            return name
    return ""


def _headline_terms(title: str) -> set[str]:
    normalized_title = re.sub(r"h[\s-]*1[\s-]*b", "h1b", title.casefold())
    return {
        term[:-1] if term.endswith("s") and len(term) > 3 and term not in {"news", "series"} else term
        for term in re.findall(r"[a-z0-9]+", normalized_title)
        if (len(term) > 2 and term not in _STOP_WORDS) or term in _NEGATION_TERMS
    }


def _topic_terms(text: str) -> set[str]:
    normalized_text = re.sub(r"h[\s-]*1[\s-]*b", "h1b", text.casefold())
    return {
        term[:-1] if term.endswith("s") and len(term) > 3 else term
        for term in re.findall(r"[a-z0-9]+", normalized_text)
        if term not in _STOP_WORDS
        and term not in _TOPIC_STOP_WORDS
        and len(term) > 1
    }


def article_matches_topic(article: dict[str, Any], topic: str) -> bool:
    """Keep an article only when its title or summary matches the search topic."""
    topic_terms = _topic_terms(topic)
    if not topic_terms:
        return False

    content_terms = _topic_terms(
        f"{article.get('title', '')} {article.get('summary', '')}"
    )
    matching_terms = topic_terms & content_terms
    required_matches = 1 if len(topic_terms) == 1 else (len(topic_terms) * 3 + 4) // 5
    return len(matching_terms) >= required_matches


def filter_saved_articles_by_topic(
    articles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter saved articles using the topic recorded when each was imported."""
    relevant_articles = []
    for article in articles:
        topic = str(article.get("search_query") or "").strip()
        if not topic or article_matches_topic(article, topic):
            relevant_articles.append(article)
    return relevant_articles


def _same_story(first: str, second: str) -> bool:
    first_terms = _headline_terms(first)
    second_terms = _headline_terms(second)
    if first_terms & _NEGATION_TERMS != second_terms & _NEGATION_TERMS:
        return False
    shared = first_terms & second_terms
    union = first_terms | second_terms
    return len(shared) >= 3 and bool(union) and len(shared) / len(union) >= 0.45


def assess_headline_coverage(
    title: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assess reports matching one headline, separately from related topic coverage."""
    matching_articles = [
        article.copy()
        for article in articles
        if _same_story(title, str(article.get("title", "")))
    ]
    outlets = sorted(
        {
            str(article.get("recognized_source", ""))
            for article in matching_articles
            if article.get("recognized_source")
            and article["recognized_source"] != "Not in recognized-source list"
        }
    )
    if len(outlets) >= 2:
        status = f"Corroborated by {len(outlets)} recognized newsrooms"
    elif outlets:
        status = "Reported by a recognized newsroom; no second match found"
    else:
        status = "No matching report found from recognized newsrooms"
    return {
        "coverage_status": status,
        "coverage_sources": ", ".join(outlets),
        "coverage_source_count": len(outlets),
        "matching_articles": matching_articles,
    }


def assess_saved_story_sources(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive same-story outlets and earliest known recognized publisher per article."""
    assessed = assess_coverage(articles)
    for article in assessed:
        related_articles = [
            other
            for other in assessed
            if other.get("url") != article.get("url")
            and _same_story(str(article.get("title", "")), str(other.get("title", "")))
        ]
        related_outlets = {
            trusted_source_name(str(other.get("source_url", "")))
            for other in related_articles
            if trusted_source_name(str(other.get("source_url", "")))
            and trusted_source_name(str(other.get("source_url", "")))
            != article["recognized_source"]
        }
        article["corroborating_outlets"] = ", ".join(sorted(related_outlets))
        article["corroboration_count"] = len(related_outlets)

        story_articles = [
            candidate
            for candidate in assessed
            if _same_story(str(article.get("title", "")), str(candidate.get("title", "")))
            and trusted_source_name(str(candidate.get("source_url", "")))
        ]
        dated_publishers = []
        for candidate in story_articles:
            published_at = _parse_publication_time(candidate.get("published_at"))
            if published_at:
                dated_publishers.append(
                    (
                        published_at,
                        trusted_source_name(str(candidate.get("source_url", ""))),
                    )
                )
        if dated_publishers:
            earliest_time = min(published_at for published_at, _ in dated_publishers)
            article["first_reported_by"] = ", ".join(
                sorted(
                    {
                        publisher
                        for published_at, publisher in dated_publishers
                        if published_at == earliest_time
                    }
                )
            )
        else:
            article["first_reported_by"] = "Not available"
    return assessed


def estimate_article_tone(text: str) -> str:
    """Estimate article wording tone with a small lexicon; this is not public sentiment."""
    positive = 0
    negative = 0
    previous_terms: list[str] = []
    for term in re.findall(r"[a-z]+", text.casefold()):
        polarity = (
            1 if term in _POSITIVE_TONE_TERMS
            else -1 if term in _NEGATIVE_TONE_TERMS
            else 0
        )
        if polarity:
            if any(previous in _TONE_NEGATIONS for previous in previous_terms[-3:]):
                polarity *= -1
            if polarity > 0:
                positive += 1
            else:
                negative += 1
        previous_terms.append(term)
    if positive > negative:
        return "Positive"
    if negative > positive:
        return "Negative"
    return "Neutral"


def _parse_publication_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def filter_recognized_sources(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only articles whose source URL belongs to a recognized newsroom."""
    return [
        article.copy()
        for article in articles
        if trusted_source_name(str(article.get("source_url", "")))
    ]


def format_fact_check_status(source_url: str, fact_check_status: str) -> str:
    """Avoid presenting an unmatched claim as unverified when its source is verified."""
    if trusted_source_name(source_url):
        if fact_check_status == "Unverified":
            return "VERIFIED"
        return f"VERIFIED source; claim: {fact_check_status}"
    return fact_check_status


def assess_coverage(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add source provenance and distinct recognized-outlet coverage per headline."""
    assessed = [article.copy() for article in articles]
    source_names = [
        trusted_source_name(str(article.get("source_url", "")))
        for article in assessed
    ]

    for index, article in enumerate(assessed):
        related_outlets = {
            source_names[other_index]
            for other_index, other in enumerate(assessed)
            if other_index != index
            and source_names[other_index]
            and source_names[other_index] != source_names[index]
            and _same_story(str(article.get("title", "")), str(other.get("title", "")))
        }
        source_name = source_names[index]
        if len(related_outlets) >= 2:
            signal = "Strong coverage signal"
        elif source_name and related_outlets:
            signal = "Recognized source with corroboration"
        elif source_name:
            signal = "Recognized newsroom"
        elif related_outlets:
            signal = "Some corroboration from recognized outlets"
        else:
            signal = "Needs verification"

        article["recognized_source"] = source_name or "Not in recognized-source list"
        article["source_verification"] = "VERIFIED" if source_name else "Unverified"
        article["coverage_signal"] = signal
        article["corroborating_outlets"] = ", ".join(sorted(related_outlets))
        article["corroboration_count"] = len(related_outlets)
    return assessed
