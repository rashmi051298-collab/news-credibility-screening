"""Train the classifier from a real CSV dataset instead of the 14-row demo dataset."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
import torch
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from transformers import DistilBertForSequenceClassification, DistilBertTokenizerFast

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL_NAME = "distilbert-base-uncased"
OUTPUT_DIR = Path("models/fake_news_distilbert")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class NewsDataset(Dataset):
    def __init__(self, texts: list[str], labels: list[int], tokenizer: DistilBertTokenizerFast, max_length: int):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        item = self.tokenizer(
            self.texts[index], truncation=True, max_length=self.max_length, return_tensors="pt"
        )
        return {key: value.squeeze(0) for key, value in item.items()} | {"labels": torch.tensor(self.labels[index])}


def collate_batch(batch: list[dict[str, torch.Tensor]], tokenizer: DistilBertTokenizerFast) -> dict[str, torch.Tensor]:
    labels = torch.stack([item.pop("labels") for item in batch])
    padded = tokenizer.pad(batch, padding=True, return_tensors="pt")
    padded["labels"] = labels
    return padded


def load_dataset(path: str) -> tuple[list[str], list[int]]:
    dataframe = pd.read_csv(path)
    required = {"title", "text", "label"}
    missing = required - set(dataframe.columns)
    if missing:
        raise ValueError(f"CSV must contain columns: {', '.join(sorted(required))}. Missing: {', '.join(sorted(missing))}")
    dataframe = dataframe.dropna(subset=["label"])
    labels = dataframe["label"].astype(int).tolist()
    if not set(labels).issubset({0, 1}) or len(set(labels)) != 2:
        raise ValueError("label must contain both classes: 0=factual and 1=fake/misleading.")
    content = (dataframe["title"].fillna("") + " [SEP] " + dataframe["text"].fillna("")).tolist()
    return content, labels


def main(dataset_path: str, epochs: int, batch_size: int = 4, max_length: int = 128, max_samples: int | None = None) -> None:
    texts, labels = load_dataset(dataset_path)
    if max_samples is not None and max_samples < len(texts):
        sampled = pd.DataFrame({"text": texts, "label": labels}).groupby("label", group_keys=False).sample(
            n=max_samples // 2, random_state=42
        )
        texts, labels = sampled["text"].tolist(), sampled["label"].tolist()
    train_texts, validation_texts, train_labels, validation_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )
    tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_NAME)
    train_data = NewsDataset(train_texts, train_labels, tokenizer, max_length)
    validation_data = NewsDataset(validation_texts, validation_labels, tokenizer, max_length)
    model = DistilBertForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2).to(DEVICE)
    optimiser = torch.optim.AdamW(model.parameters(), lr=2e-5)

    for epoch in range(epochs):
        model.train()
        for batch in DataLoader(train_data, batch_size=batch_size, shuffle=True, collate_fn=lambda batch: collate_batch(batch, tokenizer)):
            batch = {key: value.to(DEVICE) for key, value in batch.items()}
            optimiser.zero_grad()
            loss = model(**batch).loss
            loss.backward()
            optimiser.step()
        print(f"Finished epoch {epoch + 1}/{epochs}")

    model.eval()
    correct = total = 0
    with torch.inference_mode():
        for batch in DataLoader(validation_data, batch_size=batch_size, collate_fn=lambda batch: collate_batch(batch, tokenizer)):
            labels_batch = batch.pop("labels").to(DEVICE)
            outputs = model(**{key: value.to(DEVICE) for key, value in batch.items()})
            correct += (outputs.logits.argmax(dim=1) == labels_batch).sum().item()
            total += labels_batch.size(0)
    print(f"Validation accuracy: {correct / total:.2%}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"Saved trained model to {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="CSV with title,text,label columns; 0=factual, 1=fake/misleading")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4, help="Smaller values reduce memory pressure on low-memory machines.")
    parser.add_argument("--max-length", type=int, default=128, help="Shorter sequence length lowers peak memory use.")
    parser.add_argument("--max-samples", type=int, default=None, help="Optional balanced row limit for low-memory training.")
    arguments = parser.parse_args()
    main(
        arguments.dataset,
        arguments.epochs,
        batch_size=arguments.batch_size,
        max_length=arguments.max_length,
        max_samples=arguments.max_samples,
    )
