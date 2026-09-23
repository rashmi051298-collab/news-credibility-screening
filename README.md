# News Credibility Screening Dashboard

A Streamlit portfolio project that ingests Google News RSS results, stores them in SQLite, and screens an article with a trained DistilBERT classifier.

## Why this is not called a “fake news detector”

Text classification cannot establish truth. The application provides a screening signal and visible source context, while clearly stating its limitations.

## Setup

1. Install Python 3.10 or later from [python.org](https://www.python.org/downloads/).
2. Open a terminal in this folder and run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   py -m pip install -r requirements.txt
   ```

3. Download the [WELFake dataset](https://zenodo.org/records/4561253) and extract `WELFake_Dataset.csv`. It provides a large labeled dataset, but its labels are `0=fake` and `1=real`, so first prepare it for this project:

   ```powershell
   py prepare_welfake.py path\to\WELFake_Dataset.csv
   ```

4. Train the model. The prepared dataset uses `0=factual/lower-risk` and `1=fake/misleading`:

   ```powershell
   py train_model.py data\welfake_prepared.csv --epochs 1
   ```

5. Start the app:

   ```powershell
   py -m streamlit run app.py
   ```

## Included components

- `app.py`: Streamlit interface.
- `services/news_feed.py`: Google News RSS query and retrieval.
- `services/database.py`: SQLite storage; no manually written SQL is needed by the user.
- `train_model.py`: clean training and saving flow.
- `services/predictor.py`: model inference only. It never accidentally replaces a trained model.
- `prepare_welfake.py`: converts WELFake's label convention to the project's convention.

## Short description

Built a Python Streamlit news-credibility screening dashboard that ingests live Google News RSS metadata, persists deduplicated articles in SQLite, and applies a fine-tuned DistilBERT classifier with transparent model limitations and related-coverage signals.
