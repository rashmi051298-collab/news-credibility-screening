import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from services.fact_check import (
    FACTUAL,
    FAKE,
    MIXED,
    UNVERIFIED,
    classify_claim_reviews,
    classify_rating,
    describe_fact_check_status,
    search_fact_checks,
)


class FactCheckTests(unittest.TestCase):
    def test_unmatched_review_is_described_without_unverified_verdict(self) -> None:
        self.assertEqual(
            describe_fact_check_status(
                {"fact_check_status": UNVERIFIED, "fact_check_url": ""}
            ),
            "No matching published fact-check review found",
        )

    def test_ambiguous_published_review_is_not_described_as_unmatched(self) -> None:
        self.assertEqual(
            describe_fact_check_status(
                {"fact_check_status": UNVERIFIED, "fact_check_url": "https://example.test/review"}
            ),
            "Published review found; rating is unclear",
        )

    def test_failed_lookup_is_distinguished_from_no_matching_review(self) -> None:
        self.assertEqual(
            describe_fact_check_status(
                {"fact_check_status": UNVERIFIED, "fact_check_url": ""},
                "API unavailable",
            ),
            "Fact-check lookup unavailable",
        )

    def test_clear_publisher_ratings_map_to_categories(self) -> None:
        self.assertEqual(classify_rating("Mostly True"), FACTUAL)
        self.assertEqual(classify_rating("False"), FAKE)
        self.assertEqual(classify_rating("Half true"), MIXED)
        self.assertEqual(classify_rating("Needs more context"), UNVERIFIED)

    def test_unmatched_claim_stays_unverified(self) -> None:
        result = classify_claim_reviews("A headline with no matching claim", [])
        self.assertEqual(result["fact_check_status"], UNVERIFIED)
        self.assertEqual(result["fact_check_url"], "")

    def test_close_claim_match_includes_publisher_evidence(self) -> None:
        result = classify_claim_reviews(
            "The city council approved a new public park",
            [
                {
                    "text": "The city council approved a new public park",
                    "claimReview": [
                        {
                            "textualRating": "True",
                            "url": "https://fact-check.example/review",
                            "publisher": {"name": "Example Fact Check"},
                        }
                    ],
                }
            ],
        )
        self.assertEqual(result["fact_check_status"], FACTUAL)
        self.assertEqual(result["fact_check_publisher"], "Example Fact Check")
        self.assertEqual(result["fact_check_url"], "https://fact-check.example/review")

    def test_conflicting_publisher_ratings_are_not_forced_binary(self) -> None:
        result = classify_claim_reviews(
            "The city council approved a new public park",
            [
                {
                    "text": "The city council approved a new public park",
                    "claimReview": [
                        {"textualRating": "True", "url": "https://example.test/true"},
                        {"textualRating": "False", "url": "https://example.test/false"},
                    ],
                }
            ],
        )
        self.assertEqual(result["fact_check_status"], MIXED)

    def test_known_rating_with_ambiguous_second_review_is_not_forced_binary(self) -> None:
        result = classify_claim_reviews(
            "The city council approved a new public park",
            [
                {
                    "text": "The city council approved a new public park",
                    "claimReview": [
                        {"textualRating": "True", "url": "https://example.test/true"},
                        {"textualRating": "Needs more context", "url": "https://example.test/context"},
                    ],
                }
            ],
        )
        self.assertEqual(result["fact_check_status"], MIXED)

    def test_search_uses_api_response(self) -> None:
        response = {
            "claims": [
                {
                    "text": "The city council approved a new public park",
                    "claimReview": [
                        {
                            "textualRating": "False",
                            "url": "https://fact-check.example/review",
                            "publisher": {"name": "Example Fact Check"},
                        }
                    ],
                }
            ]
        }
        with patch("services.fact_check.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = BytesIO(
                json.dumps(response).encode()
            )
            result = search_fact_checks(
                "The city council approved a new public park",
                "test-api-key",
            )
        self.assertEqual(result["fact_check_status"], FAKE)

    def test_missing_api_key_fails_before_network_request(self) -> None:
        with patch("services.fact_check.urlopen") as urlopen:
            with self.assertRaisesRegex(ValueError, "GOOGLE_FACT_CHECK_API_KEY"):
                search_fact_checks("A headline", "")
        urlopen.assert_not_called()

    def test_api_error_includes_google_reason_without_leaking_key(self) -> None:
        api_key = "private-test-key"
        body = json.dumps(
            {"error": {"message": f"Invalid key {api_key}", "status": "UNAUTHENTICATED"}}
        ).encode()
        error = HTTPError(
            "https://factchecktools.googleapis.com/",
            401,
            "Unauthorized",
            {},
            BytesIO(body),
        )
        with patch("services.fact_check.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as raised:
                search_fact_checks("A headline", api_key)

        message = str(raised.exception)
        self.assertIn("Invalid key [redacted]", message)
        self.assertNotIn(api_key, message)
        self.assertIn("same Google Cloud project", message)


if __name__ == "__main__":
    unittest.main()
