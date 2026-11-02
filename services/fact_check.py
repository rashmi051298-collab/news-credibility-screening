"""Look up published fact checks for real-world news headlines."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FACT_CHECK_ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
FACTUAL = "Factual (fact-check)"
FAKE = "Fake (fact-check)"
MIXED = "Mixed / unclear"
UNVERIFIED = "Unverified"
MINIMUM_MATCH_SCORE = 0.72

_FACTUAL_RATINGS = {"true", "mostly true", "correct", "accurate"}
_FAKE_RATINGS = {"false", "mostly false", "fake", "fabricated", "pants on fire", "incorrect"}
_MIXED_RATINGS = {"half true", "partly true", "partially true", "mixed", "misleading", "out of context"}


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def classify_rating(rating: str) -> str:
    """Map only clear fact-check ratings; leave ambiguous language unclassified."""
    normalized = _normalise(rating)
    if normalized in _FACTUAL_RATINGS:
        return FACTUAL
    if normalized in _FAKE_RATINGS:
        return FAKE
    if normalized in _MIXED_RATINGS:
        return MIXED
    return UNVERIFIED


def _empty_result(status: str = UNVERIFIED) -> dict[str, str]:
    return {
        "fact_check_status": status,
        "fact_check_claim": "",
        "fact_check_rating": "",
        "fact_check_publisher": "",
        "fact_check_url": "",
        "fact_checked_at": datetime.now(timezone.utc).isoformat(),
    }


def unverified_result() -> dict[str, str]:
    """Return a timestamped unverified result for an unchecked article."""
    return _empty_result()


def describe_fact_check_status(result: dict[str, str], lookup_error: str = "") -> str:
    """Describe published-review evidence without treating missing evidence as a verdict."""
    status = result["fact_check_status"]
    if status in {FACTUAL, FAKE, MIXED}:
        return f"Fact-check rating: {status}"
    if lookup_error:
        return "Fact-check lookup unavailable"
    if result["fact_check_url"]:
        return "Published review found; rating is unclear"
    return "No matching published fact-check review found"


def classify_claim_reviews(title: str, claims: list[dict[str, Any]]) -> dict[str, str]:
    """Use a close headline-to-claim match and its cited reviews, never model guesses."""
    normalized_title = _normalise(title)
    if not normalized_title:
        raise ValueError("An article headline is required to search fact checks.")

    candidates: list[tuple[float, dict[str, Any], list[dict[str, Any]]]] = []
    for claim in claims:
        claim_text = str(claim.get("text", "")).strip()
        normalized_claim = _normalise(claim_text)
        if not normalized_claim:
            continue
        score = SequenceMatcher(None, normalized_title, normalized_claim).ratio()
        if score < MINIMUM_MATCH_SCORE:
            continue
        claim_reviews = claim.get("claimReview", [])
        if not isinstance(claim_reviews, list):
            continue
        reviews = [
            review
            for review in claim_reviews
            if isinstance(review, dict) and review.get("url") and review.get("textualRating")
        ]
        if reviews:
            candidates.append((score, claim, reviews))

    if not candidates:
        return _empty_result()

    best_score = max(candidate[0] for candidate in candidates)
    best_candidates = [candidate for candidate in candidates if best_score - candidate[0] <= 0.03]
    ratings = [
        (review, classify_rating(str(review.get("textualRating", ""))))
        for _, _, reviews in best_candidates
        for review in reviews
    ]
    classified_statuses = {status for _, status in ratings if status != UNVERIFIED}
    has_unclassified_rating = any(status == UNVERIFIED for _, status in ratings)
    if len(classified_statuses) == 1 and not has_unclassified_rating:
        status = classified_statuses.pop()
    elif classified_statuses:
        status = MIXED
    else:
        status = UNVERIFIED

    review, _ = max(
        ratings,
        key=lambda item: str(item[0].get("reviewDate", "")),
    )
    claim = max(best_candidates, key=lambda candidate: candidate[0])[1]
    publisher = review.get("publisher", {})
    return {
        "fact_check_status": status,
        "fact_check_claim": str(claim.get("text", "")),
        "fact_check_rating": str(review.get("textualRating", "")),
        "fact_check_publisher": str(publisher.get("name") or "") if isinstance(publisher, dict) else "",
        "fact_check_url": str(review.get("url", "")),
        "fact_checked_at": datetime.now(timezone.utc).isoformat(),
    }


def search_fact_checks(title: str, api_key: str, language_code: str = "en") -> dict[str, str]:
    """Query Google's Claim Search API and return a conservative, cited result."""
    if not title.strip():
        raise ValueError("An article headline is required to search fact checks.")
    if not api_key.strip():
        raise ValueError("Set the GOOGLE_FACT_CHECK_API_KEY environment variable to enable fact checks.")

    query = urlencode({"query": title.strip(), "languageCode": language_code, "pageSize": 10, "key": api_key.strip()})
    request = Request(
        f"{FACT_CHECK_ENDPOINT}?{query}",
        headers={"Accept": "application/json", "User-Agent": "NewsCredibilityScreening/1.0"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except HTTPError as error:
        try:
            error_payload = json.loads(error.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            error_payload = {}
        api_error = error_payload.get("error", {}) if isinstance(error_payload, dict) else {}
        api_message = api_error.get("message", "") if isinstance(api_error, dict) else ""
        if api_message:
            api_message = str(api_message).replace(api_key.strip(), "[redacted]")[:500]
            detail = f" Google says: {api_message}"
        else:
            detail = ""
        if error.code == 401:
            guidance = (
                " Check that the key is valid, the Fact Check Tools API is enabled in the same "
                "Google Cloud project, and the key's API restrictions allow it."
            )
        else:
            guidance = " Check API access, key restrictions, and quota."
        raise RuntimeError(
            f"Google Fact Check API returned HTTP {error.code}.{detail}{guidance}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Could not reach the Google Fact Check API. Check the connection and try again.") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("Google Fact Check API returned an invalid response.") from error

    if not isinstance(payload, dict):
        raise RuntimeError("Google Fact Check API returned an invalid response.")
    claims = payload.get("claims", [])
    if not isinstance(claims, list) or not all(isinstance(claim, dict) for claim in claims):
        raise RuntimeError("Google Fact Check API returned an invalid claims list.")
    return classify_claim_reviews(title, claims)
