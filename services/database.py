"""Small SQLite repository. Keeps database access out of the Streamlit UI."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "news_credibility.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                summary TEXT,
                source TEXT,
                url TEXT NOT NULL UNIQUE,
                published_at TEXT,
                search_query TEXT,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def save_articles(articles: list[dict[str, Any]]) -> int:
    """Insert new articles and return how many were not already stored."""
    if not articles:
        return 0

    with get_connection() as connection:
        before = connection.total_changes
        connection.executemany(
            """
            INSERT OR IGNORE INTO articles
                (title, summary, source, url, published_at, search_query)
            VALUES (:title, :summary, :source, :url, :published_at, :search_query)
            """,
            articles,
        )
        return connection.total_changes - before


def list_articles(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM articles
            ORDER BY COALESCE(published_at, imported_at) DESC
            LIMIT ?
            """,
            (limit,),
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
