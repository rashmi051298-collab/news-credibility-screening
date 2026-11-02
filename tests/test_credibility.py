import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from services.credibility import (
    assess_coverage,
    assess_headline_coverage,
    assess_saved_story_sources,
    article_matches_topic,
    estimate_article_tone,
    filter_recognized_sources,
    filter_saved_articles_by_topic,
    format_fact_check_status,
    trusted_source_name,
)
from services.news_feed import fetch_google_news


class CredibilityTests(unittest.TestCase):
    def test_topic_filter_keeps_matching_articles_and_excludes_loose_matches(self) -> None:
        articles = [
            {
                "title": "India election commission announces a new voting schedule",
                "summary": "The election schedule was announced today.",
            },
            {
                "title": "India cricket team wins the championship",
                "summary": "A major sports story from India.",
            },
        ]

        self.assertTrue(article_matches_topic(articles[0], "India election"))
        self.assertFalse(article_matches_topic(articles[1], "India election"))

    def test_saved_library_articles_are_filtered_by_their_original_search_query(self) -> None:
        articles = [
            {
                "title": "India election commission announces new voting schedule",
                "search_query": "India election",
            },
            {
                "title": "India cricket team wins championship",
                "search_query": "India election",
            },
            {"title": "Legacy headline with no stored topic", "search_query": ""},
            {"title": "Legacy headline with null topic", "search_query": None},
        ]

        filtered = filter_saved_articles_by_topic(articles)

        self.assertEqual(
            [article["title"] for article in filtered],
            [
                "India election commission announces new voting schedule",
                "Legacy headline with no stored topic",
                "Legacy headline with null topic",
            ],
        )

    def test_article_tone_is_estimated_separately_from_fact_check_status(self) -> None:
        self.assertEqual(estimate_article_tone("The project succeeded with good growth"), "Positive")
        self.assertEqual(estimate_article_tone("War brings loss and fear"), "Negative")
        self.assertEqual(estimate_article_tone("This is not good"), "Negative")
        self.assertEqual(estimate_article_tone("News update today"), "Neutral")

    def test_saved_story_lists_other_outlet_and_earliest_reporter(self) -> None:
        articles = assess_saved_story_sources(
            [
                {
                    "title": "Trump to end H-1B visa deference",
                    "source_url": "https://www.reuters.com",
                    "published_at": "Fri, 30 Oct 2026 08:00:00 GMT",
                    "url": "https://reuters.com/story",
                },
                {
                    "title": "Trump H1B visa policy ends prior deference",
                    "source_url": "https://apnews.com",
                    "published_at": "Fri, 30 Oct 2026 08:30:00 GMT",
                    "url": "https://apnews.com/story",
                },
            ]
        )

        self.assertEqual(articles[0]["corroborating_outlets"], "Associated Press")
        self.assertEqual(articles[1]["corroborating_outlets"], "Reuters")
        self.assertEqual(articles[0]["first_reported_by"], "Reuters")
        self.assertEqual(articles[1]["first_reported_by"], "Reuters")

    def test_verified_source_hides_unmatched_claim_status(self) -> None:
        self.assertEqual(
            format_fact_check_status("https://www.reuters.com/article", "Unverified"),
            "VERIFIED",
        )

    def test_verified_source_keeps_available_fact_check_result(self) -> None:
        self.assertEqual(
            format_fact_check_status("https://www.reuters.com/article", "Factual"),
            "VERIFIED source; claim: Factual",
        )
        self.assertEqual(
            format_fact_check_status("https://unknown.example/article", "Factual"),
            "Factual",
        )

    def test_unverified_source_keeps_unmatched_claim_status(self) -> None:
        self.assertEqual(
            format_fact_check_status("https://unknown.example/article", "Unverified"),
            "Unverified",
        )

    def test_recognized_source_requires_matching_publisher_domain(self) -> None:
        self.assertEqual(trusted_source_name("https://www.reuters.com/world"), "Reuters")
        self.assertEqual(trusted_source_name("https://reuters.com.attacker.test"), "")
        self.assertEqual(trusted_source_name(""), "")

    def test_similar_headlines_show_distinct_recognized_outlets(self) -> None:
        articles = assess_coverage(
            [
                {
                    "title": "India election commission announces new voting schedule",
                    "source_url": "https://www.reuters.com",
                },
                {
                    "title": "India election commission announces voting schedule",
                    "source_url": "https://apnews.com",
                },
                {
                    "title": "India election commission announces new voting schedule",
                    "source_url": "https://www.bbc.com",
                },
            ]
        )

        self.assertEqual(articles[0]["coverage_signal"], "Strong coverage signal")
        self.assertEqual(articles[0]["corroboration_count"], 2)
        self.assertIn("Associated Press", articles[0]["corroborating_outlets"])

    def test_single_article_is_not_marked_as_factual(self) -> None:
        article = assess_coverage(
            [{"title": "A unique headline", "source_url": "https://www.reuters.com"}]
        )[0]
        self.assertEqual(article["coverage_signal"], "Recognized newsroom")
        self.assertEqual(article["source_verification"], "VERIFIED")
        self.assertNotIn("factual", article["coverage_signal"].casefold())

    def test_unrecognized_source_is_not_verified(self) -> None:
        article = assess_coverage(
            [{"title": "A unique headline", "source_url": "https://unknown.example"}]
        )[0]
        self.assertEqual(article["source_verification"], "Unverified")

    def test_unrecognized_sources_are_excluded_from_news_list(self) -> None:
        articles = assess_coverage(
            [
                {"title": "Trusted story", "source_url": "https://www.reuters.com/world"},
                {"title": "Unknown story", "source_url": "https://unknown.example/story"},
            ]
        )

        filtered = filter_recognized_sources(articles)
        self.assertEqual([article["title"] for article in filtered], ["Trusted story"])

    def test_negated_headline_is_not_counted_as_matching_coverage(self) -> None:
        articles = assess_coverage(
            [
                {
                    "title": "City council approves new public park",
                    "source_url": "https://www.reuters.com",
                },
                {
                    "title": "City council does not approve new public park",
                    "source_url": "https://apnews.com",
                },
            ]
        )

        self.assertEqual(articles[0]["corroboration_count"], 0)

    def test_headline_check_returns_distinct_current_outlet_matches(self) -> None:
        headline = "Trump to end H-1B visa deference"
        articles = assess_coverage(
            [
                {
                    "title": "Trump to end H-1B visa deference, memo says - Reuters",
                    "source_url": "https://www.reuters.com",
                },
                {
                    "title": "Trump H1B visa policy ends prior deference - AP News",
                    "source_url": "https://apnews.com",
                },
                {
                    "title": "Trump raises H-1B visa fee - Reuters",
                    "source_url": "https://www.reuters.com",
                },
            ]
        )

        result = assess_headline_coverage(headline, articles)
        self.assertEqual(len(result["matching_articles"]), 2)
        self.assertEqual(result["coverage_status"], "Corroborated by 2 recognized newsrooms")
        self.assertEqual(result["coverage_sources"], "Associated Press, Reuters")
        self.assertEqual(result["coverage_source_count"], 2)

    def test_unmatched_headline_does_not_get_confirmed_by_related_topic(self) -> None:
        headline = "Trump to end H-1B visa deference"
        articles = assess_coverage(
            [
                {
                    "title": "Trump raises H-1B visa fee - Reuters",
                    "source_url": "https://www.reuters.com",
                }
            ]
        )

        result = assess_headline_coverage(headline, articles)
        self.assertEqual(len(result["matching_articles"]), 0)
        self.assertEqual(result["coverage_source_count"], 0)
        self.assertEqual(
            result["coverage_status"],
            "No matching report found from recognized newsrooms",
        )

    def test_news_feed_filters_by_publisher_domain_and_keeps_source_link(self) -> None:
        import feedparser

        entries = [
            feedparser.FeedParserDict(
                {
                    "title": "India election headline - Reuters",
                    "link": "https://news.google.com/articles/1",
                    "source": {"title": "Reuters", "href": "https://www.reuters.com"},
                    "published": "Fri, 30 Oct 2026 08:32:32 GMT",
                    "summary": "Example summary",
                }
            ),
            feedparser.FeedParserDict(
                {
                    "title": "India election headline - Fake Reuters",
                    "link": "https://news.google.com/articles/2",
                    "source": {"title": "Fake Reuters", "href": "https://reuters.com.attacker.test"},
                    "published": "Fri, 30 Oct 2026 08:32:32 GMT",
                    "summary": "Example summary",
                }
            ),
        ]
        feed = feedparser.FeedParserDict({"entries": entries, "bozo": False})
        with patch("services.news_feed.feedparser.parse", return_value=feed) as parse:
            articles = fetch_google_news("India election", limit=5)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source_url"], "https://www.reuters.com")
        query = parse_qs(urlsplit(parse.call_args.args[0]).query)["q"][0]
        self.assertIn("site:reuters.com", query)

    def test_news_feed_discards_off_topic_results(self) -> None:
        import feedparser

        feed = feedparser.FeedParserDict(
            {
                "entries": [
                    feedparser.FeedParserDict(
                        {
                            "title": "India cricket team wins championship",
                            "summary": "India celebrated a major sports result.",
                            "link": "https://news.google.com/articles/off-topic",
                            "source": {"title": "Reuters", "href": "https://www.reuters.com"},
                        }
                    ),
                    feedparser.FeedParserDict(
                        {
                            "title": "India election commission announces a new voting schedule",
                            "summary": "The election schedule was announced today.",
                            "link": "https://news.google.com/articles/on-topic",
                            "source": {"title": "Reuters", "href": "https://www.reuters.com"},
                        }
                    ),
                ],
                "bozo": False,
            }
        )
        with patch("services.news_feed.feedparser.parse", return_value=feed):
            articles = fetch_google_news("India election", limit=1)

        self.assertEqual(len(articles), 1)
        self.assertIn("election", articles[0]["title"].casefold())


if __name__ == "__main__":
    unittest.main()
