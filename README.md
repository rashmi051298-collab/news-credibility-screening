# News Credibility Screening Dashboard

A real-world news dashboard that collects current headlines and checks them against published fact-check reviews. It does not independently verify every statement in an article.

## Overview

This project builds a decision-support dashboard that collects live news headlines and looks up closely matching claims reviewed by fact-check publishers. It combines:
- live Google News RSS retrieval
- local SQLite storage for headline metadata and review results
- Google Fact Check Tools API lookups with linked review evidence
- publisher-domain provenance and cross-outlet coverage signals
- a Streamlit dashboard for user interaction

## Problem

Misinformation spreads quickly across digital media. A simple way to support readers is to provide a lightweight credibility screening tool that can assess article text and flag suspicious content.

## Tech Stack

- Python 3.12
- Streamlit
- Pandas
- SQLite
- Google News RSS
- Google Fact Check Tools API

## Project Structure

- `app.py` — Streamlit dashboard
- `train_model.py`, `prepare_welfake.py` — optional legacy classifier training utilities; not used for live fact-check labels
- `services/database.py` — SQLite operations
- `services/news_feed.py` — Google News RSS feed logic
- `services/predictor.py` — model inference logic
- `data/` — prepared dataset and raw source data
- `models/fake_news_distilbert/` — trained model checkpoint

## Features

- Fetches current Google News headlines and feed metadata
- Shows ten live trending headlines across India and world coverage, balanced across broad news sectors
- In “Get news,” choose recognized newsrooms only or all Google News results; recognized publisher domains are marked `VERIFIED` for source identity
- Filters search results by significant words in the requested topic, including saved library articles with a recorded search topic
- Refresh controls clear the active search and its displayed results; saved library articles remain stored
- Saves article metadata into a local database
- Filters “Get news” results to a curated list of recognized newsrooms when that publisher option is selected
- Compares similar headlines across different recognized outlets
- Shows factual, fake, mixed/unclear, or unverified statuses based on published fact-check ratings
- Links categorized results to the fact-check publisher's review
- Provides a local news library for review
- Groups saved library articles by the month they were saved in India Standard Time and shows each save time in IST
- Lists other recognized outlets covering a similar story and the earliest reported outlet when publication timestamps are available
- Stores an automated article-wording tone estimate (positive, negative, or neutral) separately from published fact-check ratings
- Supports dataset preparation from WELFake

## Live fact-checking

Google News RSS supplies current headlines; it does not supply truth labels. The dashboard searches the Google Fact Check Tools Claim Search API and only assigns “Factual” or “Fake” when a closely matching claim has a clear published rating. Mixed or conflicting ratings are shown as “Mixed / unclear.” When a review is absent or inconclusive, the interface says no matching review was found or that its rating is unclear, rather than presenting that as a verdict. A fact-check rating applies to the reviewed claim, not necessarily every statement in an article.

“Get news” offers “Recognized newsrooms only” and “All Google News results.” The first uses the explicit publisher-domain list in `services/credibility.py`; the second may include unrecognized sources. `VERIFIED` means the publisher domain is on that list; it does not verify the headline's claims. The headline checker displays the number and names of recognized publishers with matching reports returned by Google News, separately from published fact-check results. This is not an exhaustive search of every newspaper or channel in India or worldwide, and multiple reports do not prove a story true; read the linked original reports and claim review.

The news tables' positive/negative/neutral article-tone estimate is calculated from headline and feed summary wording. It is not a measurement of public opinion and is kept separate from the fact-check publisher's rating. “First reported by” is derived from the earliest publication timestamp available among similar saved reports; it is separate from the fact-check publisher.

In the news tables, a recognized source with no matching published claim review is shown as `VERIFIED` only; the table does not add a confusing `Unverified` claim label. When a matching review provides a result, the table shows both the verified source and that claim result (for example, `VERIFIED source; claim: Factual (fact-check)`). Source verification still confirms the publisher domain only, not the truth of a headline.

The “Get news” tab loads its top-ten India and world section from Google News topic feeds when the app session starts. Use “Refresh trending news” to fetch the latest feed results while the app is open. It draws from national/world affairs, business, technology, science, health, sports, and entertainment, while balancing the selection across India and world coverage. These are live headlines surfaced by Google News, not a separately measured popularity score; dates and publisher links are shown with each result. Only sources on the recognized-domain list are included.

The [Fact Check Tools API](https://developers.google.com/fact-check/tools/api) requires an API key. Enable the API for a Google Cloud project and set the key in the same PowerShell session before starting the app:

```powershell
$env:GOOGLE_FACT_CHECK_API_KEY = "YOUR_API_KEY"
python -m streamlit run app.py
```

Do not commit the key. Without it, Google News headlines are still collected and stored, and recognized publisher domains show as `VERIFIED`. Published claim reviews are only shown when the API returns a matching review with a classifiable result.

## Setup

1. Clone the repository
2. Create a Python 3.12 virtual environment
3. Install dependencies
4. Configure a Google Fact Check Tools API key (optional, required for published fact-check lookups)
5. Run the app

Example:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GOOGLE_FACT_CHECK_API_KEY = "YOUR_API_KEY"
python -m streamlit run app.py
```

## Usage

- Open the Streamlit app
- Search for a topic in the “Get news” tab
- Review the live top-ten section or select “Refresh trending news” to retrieve current India and world headlines
- Fetch and save the current headlines, then review their fact-check status and source links
- Use “Refresh search” to clear a search phrase and its displayed results, or “Refresh library” to reload saved articles without deleting them
- Use the “Fact-check a claim” tab to search a specific headline against current recognized-newsroom coverage and published claim reviews
- Open the linked reports and review to confirm they cover the same claim

## Notes

This project is a fact-check lookup aid, not an automated truth detector. A missing review is not evidence that a claim is factual or fake. Always read the cited review, verify that it addresses the same claim, and consult independent sources for consequential decisions.

## Short description

Built a Python Streamlit dashboard that ingests live Google News headlines, stores them in SQLite, and links close claim matches to published Google Fact Check Tools reviews.
