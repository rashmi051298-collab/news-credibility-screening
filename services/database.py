"""Small SQLite repository. Keeps database access out of the Streamlit UI."""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Iterator

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "news_credibility.db"
INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialise_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                summary TEXT,
                source TEXT,
                source_url TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL UNIQUE,
                published_at TEXT,
                search_query TEXT,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                recognized_source TEXT NOT NULL DEFAULT 'Not assessed',
                coverage_signal TEXT NOT NULL DEFAULT 'Needs verification',
                corroborating_outlets TEXT NOT NULL DEFAULT '',
                corroboration_count INTEGER NOT NULL DEFAULT 0,
                first_reported_by TEXT NOT NULL DEFAULT 'Not available',
                article_tone TEXT NOT NULL DEFAULT 'Not assessed',
                fact_check_status TEXT NOT NULL DEFAULT 'Unverified',
                fact_check_claim TEXT NOT NULL DEFAULT '',
                fact_check_rating TEXT NOT NULL DEFAULT '',
                fact_check_publisher TEXT NOT NULL DEFAULT '',
                fact_check_url TEXT NOT NULL DEFAULT '',
                fact_checked_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(articles)")}
        credibility_columns = {
            "source_url": "TEXT NOT NULL DEFAULT ''",
            "recognized_source": "TEXT NOT NULL DEFAULT 'Not assessed'",
            "coverage_signal": "TEXT NOT NULL DEFAULT 'Needs verification'",
            "corroborating_outlets": "TEXT NOT NULL DEFAULT ''",
            "corroboration_count": "INTEGER NOT NULL DEFAULT 0",
            "first_reported_by": "TEXT NOT NULL DEFAULT 'Not available'",
            "article_tone": "TEXT NOT NULL DEFAULT 'Not assessed'",
        }
        for column, definition in credibility_columns.items():
            if column not in columns:
                connection.execute(f"ALTER TABLE articles ADD COLUMN {column} {definition}")
        columns.update(credibility_columns)
        fact_check_columns = {
            "fact_check_status": "TEXT NOT NULL DEFAULT 'Unverified'",
            "fact_check_claim": "TEXT NOT NULL DEFAULT ''",
            "fact_check_rating": "TEXT NOT NULL DEFAULT ''",
            "fact_check_publisher": "TEXT NOT NULL DEFAULT ''",
            "fact_check_url": "TEXT NOT NULL DEFAULT ''",
            "fact_checked_at": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in fact_check_columns.items():
            if column not in columns:
                connection.execute(f"ALTER TABLE articles ADD COLUMN {column} {definition}")


def save_articles(articles: list[dict[str, Any]]) -> int:
    """Insert new articles and return how many were not already stored."""
    if not articles:
        return 0

    records = [
        {
            **article,
            "source_url": article.get("source_url", ""),
            "recognized_source": article.get("recognized_source", "Not assessed"),
            "coverage_signal": article.get("coverage_signal", "Needs verification"),
            "corroborating_outlets": article.get("corroborating_outlets", ""),
            "corroboration_count": article.get("corroboration_count", 0),
            "first_reported_by": article.get("first_reported_by", "Not available"),
            "article_tone": article.get("article_tone", "Not assessed"),
        }
        for article in articles
    ]
    with get_connection() as connection:
        before = connection.total_changes
        connection.executemany(
            """
            INSERT OR IGNORE INTO articles
                (title, summary, source, source_url, url, published_at, search_query,
                 recognized_source, coverage_signal, corroborating_outlets, corroboration_count,
                 first_reported_by, article_tone)
            VALUES (:title, :summary, :source, :source_url, :url, :published_at, :search_query,
                    :recognized_source, :coverage_signal, :corroborating_outlets, :corroboration_count,
                    :first_reported_by, :article_tone)
            """,
            records,
        )
        return connection.total_changes - before


def update_article_fact_check(article: dict[str, Any]) -> None:
    """Save a fact-check result for an already stored article."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE articles
            SET fact_check_status = :fact_check_status,
                fact_check_claim = :fact_check_claim,
                fact_check_rating = :fact_check_rating,
                fact_check_publisher = :fact_check_publisher,
                fact_check_url = :fact_check_url,
                fact_checked_at = :fact_checked_at
            WHERE url = :url
            """,
            article,
        )


def list_articles(limit: int | None = None) -> list[dict[str, Any]]:
    with get_connection() as connection:
        query = """
            SELECT * FROM articles
            ORDER BY imported_at DESC, id DESC
        """
        if limit is not None:
            query += " LIMIT ?"
            rows = connection.execute(query, (limit,)).fetchall()
        else:
            rows = connection.execute(query).fetchall()
    return [dict(row) for row in rows]


def group_articles_by_saved_month(
    articles: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group saved articles by import month in India Standard Time."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for article in articles:
        imported_at = datetime.fromisoformat(str(article["imported_at"]).replace("Z", "+00:00"))
        if imported_at.tzinfo is None:
            imported_at = imported_at.replace(tzinfo=timezone.utc)
        saved_at_ist = imported_at.astimezone(INDIA_TIMEZONE)
        group_name = saved_at_ist.strftime("%B %Y")
        grouped_article = article.copy()
        grouped_article["saved_at_ist"] = saved_at_ist.strftime(
            "%d %b %Y, %I:%M:%S %p IST"
        )
        groups.setdefault(group_name, []).append(grouped_article)
    return list(groups.items())


def update_article_credibility(article: dict[str, Any]) -> None:
    """Save publisher provenance and related recognized-outlet coverage."""
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE articles
            SET source_url = :source_url,
                recognized_source = :recognized_source,
                coverage_signal = :coverage_signal,
                corroborating_outlets = :corroborating_outlets,
                corroboration_count = :corroboration_count,
                first_reported_by = :first_reported_by
            WHERE url = :url
            """,
            article,
        )


def update_article_tone(article: dict[str, Any]) -> None:
    """Save an estimated article-wording tone, separate from fact-check ratings."""
    with get_connection() as connection:
        connection.execute(
            "UPDATE articles SET article_tone = :article_tone WHERE url = :url",
            article,
        )


def find_related_articles(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch locally saved coverage related to a topic or headline for extra context."""
    if not query or not query.strip():
        return []

    normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", query.lower())
    words = [word for word in normalized.split() if len(word) >= 3][:6]
    if not words:
        return []

    conditions = " OR ".join("(LOWER(title) LIKE ? OR LOWER(summary) LIKE ?)" for _ in words)
    parameters = []
    for word in words:
        parameters.extend([f"%{word}%", f"%{word}%"])

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM articles
            WHERE {conditions}
            ORDER BY imported_at DESC
            LIMIT ?
            """,
            parameters + [limit],
        ).fetchall()
    return [dict(row) for row in rows]


def count_related_articles(title: str) -> int:
    """A lightweight local related-coverage signal based on significant title words."""
    words = [word for word in title.lower().split() if len(word) >= 5][:3]
    if not words:
        return 0
    where = " OR ".join("LOWER(title) LIKE ?" for _ in words)
    with get_connection() as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS count FROM articles WHERE {where}",
            [f"%{word}%" for word in words],
        ).fetchone()
    return max(0, int(row["count"]) - 1)
