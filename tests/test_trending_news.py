import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from services.news_feed import fetch_trending_news, google_news_topic_rss_url


class TrendingNewsTests(unittest.TestCase):
    def test_topic_feed_url_uses_region_and_topic(self) -> None:
        url = google_news_topic_rss_url("BUSINESS", "IN")
        parsed_url = urlsplit(url)

        self.assertIn("/topic/BUSINESS", parsed_url.path)
        self.assertEqual(
            parse_qs(parsed_url.query),
            {"hl": ["en-IN"], "gl": ["IN"], "ceid": ["IN:en"]},
        )

    def test_fetch_returns_ten_sector_diverse_headlines_balanced_by_region(self) -> None:
        def fake_topic_feed(url: str):
            topic = urlsplit(url).path.rsplit("/", 1)[-1]
            region = "India" if parse_qs(urlsplit(url).query)["gl"] == ["IN"] else "World"
            entries = [
                {
                    "title": f"{region} {topic} headline {index}",
                    "link": f"https://news.google.com/{region}/{topic}/{index}",
                    "source": {"title": "Reuters", "href": "https://www.reuters.com"},
                    "published": f"Fri, 30 Oct 2026 08:{index:02d}:00 GMT",
                }
                for index in range(3)
            ]
            return SimpleNamespace(bozo=False, entries=entries)

        with patch("services.news_feed._parse_remote_feed", side_effect=fake_topic_feed):
            articles, errors = fetch_trending_news()

        self.assertEqual(len(articles), 10)
        self.assertEqual(errors, [])
        self.assertEqual(
            {region: sum(article["region"] == region for article in articles) for region in ("India", "World")},
            {"India": 5, "World": 5},
        )
        self.assertEqual(
            {article["sector"] for article in articles},
            {
                "National affairs",
                "World affairs",
                "Business",
                "Technology",
                "Science",
                "Health",
                "Sports",
                "Entertainment",
            },
        )
        self.assertLessEqual(
            max(Counter(article["sector"] for article in articles).values()),
            2,
        )

    def test_partial_topic_feed_failures_are_reported_with_available_headlines(self) -> None:
        def partly_available_feed(url: str):
            topic = urlsplit(url).path.rsplit("/", 1)[-1]
            if topic != "NATION":
                raise RuntimeError("Unavailable")
            return SimpleNamespace(
                bozo=False,
                entries=[
                    {
                        "title": "India headline",
                        "link": "https://news.google.com/india/nation/1",
                        "source": {"title": "Reuters", "href": "https://www.reuters.com"},
                    }
                ],
            )

        with patch("services.news_feed._parse_remote_feed", side_effect=partly_available_feed):
            articles, errors = fetch_trending_news()

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["region"], "India")
        self.assertEqual(len(errors), 13)

    def test_all_topic_feed_failures_raise_an_error(self) -> None:
        with patch(
            "services.news_feed._parse_remote_feed",
            side_effect=RuntimeError("Unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Could not load any live"):
                fetch_trending_news()

    def test_invalid_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 1"):
            fetch_trending_news(limit=0)


if __name__ == "__main__":
    unittest.main()
