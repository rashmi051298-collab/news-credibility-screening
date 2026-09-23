# News Credibility Screening Dashboard

A real-world NLP and ML project that screens article headlines and summaries for credibility using a fine-tuned DistilBERT model.

## Overview

This project builds a decision-support dashboard for evaluating whether a news article appears more likely to be factual or misleading. It combines:
- live Google News RSS retrieval
- local SQLite storage for saved articles
- NLP preprocessing
- transformer-based classification
- a Streamlit dashboard for user interaction

## Problem

Misinformation spreads quickly across digital media. A simple way to support readers is to provide a lightweight credibility screening tool that can assess article text and flag suspicious content.

## Tech Stack

- Python
- Streamlit
- DistilBERT
- Transformers
- PyTorch
- Pandas
- SQLite
- Google News RSS
- Scikit-learn

## Project Structure

- `app.py` — Streamlit dashboard
- `train_model.py` — model training pipeline
- `prepare_welfake.py` — dataset preparation
- `services/database.py` — SQLite operations
- `services/news_feed.py` — Google News RSS feed logic
- `services/predictor.py` — model inference logic
- `data/` — prepared dataset and raw source data
- `models/fake_news_distilbert/` — trained model checkpoint

## Features

- Fetches current Google News articles
- Saves article metadata into a local database
- Screens article titles and summaries using a trained transformer
- Displays confidence scores
- Provides a local news library for review
- Supports dataset preparation from WELFake

## Dataset

The project uses the WELFake dataset for fake vs factual classification. The dataset is prepared into a structured CSV format before training.

## Model

The model is based on DistilBERT and fine-tuned for binary classification:
- 0 = factual / lower-risk
- 1 = fake / misleading

## Setup

1. Clone the repository
2. Create a virtual environment
3. Install dependencies
4. Prepare the dataset
5. Train the model
6. Run the app

Example:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python prepare_welfake.py data\raw\WELFake_Dataset.csv
python train_model.py data\welfake_prepared.csv --epochs 1 --batch-size 2 --max-length 64 --max-samples 2000
python -m streamlit run app.py
```

## Usage

- Open the Streamlit app
- Search for a topic in the “Get news” tab
- Save relevant news articles
- Open the “Screen article” tab
- Enter a headline and article text
- View the credibility result and confidence score

## Notes

This project is intended as a decision-support tool, not a definitive fact-checking system. It should be used alongside source verification and professional journalism practices.

## Future Improvements

- Add explainability with SHAP or LIME
- Improve dataset balancing
- Add multi-label classification or rumor detection
- Deploy to Streamlit Cloud or Hugging Face Spaces
- Add model evaluation metrics and charts

## Resume description

Built a Python Streamlit news-credibility screening dashboard that ingests live Google News RSS metadata, persists deduplicated articles in SQLite, and applies a fine-tuned DistilBERT classifier with transparent model limitations and related-coverage signals.
