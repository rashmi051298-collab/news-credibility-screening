"""Inference only: never initialise a new model here, preventing accidental untrained predictions."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import torch
from transformers import DistilBertForSequenceClassification, DistilBertTokenizerFast

BASE_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = BASE_DIR / "models" / "fake_news_distilbert"
LABELS = {
    0: "Not flagged as fake/misleading (unverified)",
    1: "Potentially fake or misleading",
}


@lru_cache(maxsize=1)
def _load_model() -> tuple[DistilBertTokenizerFast, DistilBertForSequenceClassification]:
    if not MODEL_DIR.exists():
        raise FileNotFoundError("No trained model found. Run train_model.py with a labeled dataset first.")
    tokenizer = DistilBertTokenizerFast.from_pretrained(str(MODEL_DIR))
    model = DistilBertForSequenceClassification.from_pretrained(str(MODEL_DIR))
    model.eval()
    return tokenizer, model


@torch.inference_mode()
def screen_article(title: str, text: str) -> tuple[str, float]:
    tokenizer, model = _load_model()
    input_text = f"{title} [SEP] {text}".strip()
    inputs = tokenizer(input_text, return_tensors="pt", truncation=True, max_length=256)
    probabilities = torch.softmax(model(**inputs).logits, dim=1)[0]
    # Class 0 is the dataset's real class; the prediction does not verify this article.
    label_id = int(torch.argmax(probabilities).item())
    return LABELS[label_id], float(probabilities[label_id].item() * 100)
