"""Convert WELFake source labels for the optional legacy classifier training pipeline.

WELFake uses 0=fake and 1=real. These remain dataset-provided labels, not live
fact-check results or independent verification of every article.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main(input_path: str, output_path: str) -> None:
    dataframe = pd.read_csv(input_path)
    column_map = {column.lower(): column for column in dataframe.columns}
    required = {"title", "text", "label"}
    missing = required - set(column_map)
    if missing:
        raise ValueError(f"The source file is missing: {', '.join(sorted(missing))}")

    clean = dataframe[[column_map["title"], column_map["text"], column_map["label"]]].copy()
    clean.columns = ["title", "text", "source_label"]
    clean = clean.dropna(subset=["source_label"])
    clean["source_label"] = clean["source_label"].astype(int)
    if not set(clean["source_label"]).issubset({0, 1}):
        raise ValueError("Expected WELFake labels 0=fake and 1=real.")
    clean["label"] = clean["source_label"].map({0: 1, 1: 0})
    clean = clean.drop(columns="source_label")
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(destination, index=False)
    print(f"Prepared {len(clean):,} records at {destination}")
    print("Training labels: 0=dataset-labeled real, 1=dataset-labeled fake")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Path to WELFake_Dataset.csv")
    parser.add_argument("--output", default="data/welfake_prepared.csv")
    args = parser.parse_args()
    main(args.input, args.output)
