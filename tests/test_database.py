import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.database import (
    group_articles_by_saved_month,
    initialise_database,
    list_articles,
    save_articles,
    update_article_fact_check,
)


class DatabaseMigrationTests(unittest.TestCase):
    def test_library_groups_saved_articles_by_ist_month_and_formats_ist_time(self) -> None:
        groups = group_articles_by_saved_month(
            [
                {
                    "title": "Saved in October in IST",
                    "imported_at": "2026-10-30 20:00:00",
                },
                {
                    "title": "Another October save",
                    "imported_at": "2026-10-30T20:01:00+00:00",
                },
                {
                    "title": "Saved in September in IST",
                    "imported_at": "2026-09-30T17:00:00+00:00",
                },
            ]
        )

        self.assertEqual(
            [date for date, _ in groups],
            ["October 2026", "September 2026"],
        )
        self.assertEqual(len(groups[0][1]), 2)
        self.assertEqual(
            groups[0][1][0]["saved_at_ist"],
            "31 Oct 2026, 01:30:00 AM IST",
        )
        self.assertEqual(
            groups[1][1][0]["saved_at_ist"],
            "30 Sep 2026, 10:30:00 PM IST",
        )

    def test_existing_article_database_gets_unverified_fact_check_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "articles.db"
            with sqlite3.connect(database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE articles (
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
                connection.execute(
                    """
                    INSERT INTO articles (title, url)
                    VALUES ('Previously stored headline', 'https://example.test/article')
                    """
                )
            connection.close()

            with patch("services.database.DB_PATH", database_path):
                initialise_database()
                save_articles(
                    [
                        {
                            "title": "New headline",
                            "summary": "",
                            "source": "Example News",
                            "url": "https://example.test/new",
                            "published_at": "",
                            "search_query": "test",
                            "first_reported_by": "Reuters",
                            "article_tone": "Positive",
                        }
                    ]
                )
                update_article_fact_check(
                    {
                        "url": "https://example.test/new",
                        "fact_check_status": "Fake (fact-check)",
                        "fact_check_claim": "New headline",
                        "fact_check_rating": "False",
                        "fact_check_publisher": "Example Fact Check",
                        "fact_check_url": "https://example.test/review",
                        "fact_checked_at": "2026-10-30T00:00:00+00:00",
                    }
                )
                articles = list_articles()

            old_article = next(article for article in articles if article["title"] == "Previously stored headline")
            new_article = next(article for article in articles if article["title"] == "New headline")
            self.assertEqual(old_article["fact_check_status"], "Unverified")
            self.assertEqual(old_article["fact_check_url"], "")
            self.assertEqual(old_article["recognized_source"], "Not assessed")
            self.assertEqual(old_article["coverage_signal"], "Needs verification")
            self.assertEqual(new_article["fact_check_status"], "Fake (fact-check)")
            self.assertEqual(new_article["fact_check_url"], "https://example.test/review")
            self.assertEqual(new_article["article_tone"], "Positive")
            self.assertEqual(new_article["first_reported_by"], "Reuters")

    def test_list_articles_returns_all_saved_articles_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "articles.db"
            with patch("services.database.DB_PATH", database_path):
                initialise_database()
                save_articles(
                    [
                        {
                            "title": f"Headline {index}",
                            "summary": "",
                            "source": "Example News",
                            "url": f"https://example.test/{index}",
                            "published_at": "",
                            "search_query": "test",
                        }
                        for index in range(105)
                    ]
                )
                self.assertEqual(len(list_articles()), 105)


if __name__ == "__main__":
    unittest.main()
