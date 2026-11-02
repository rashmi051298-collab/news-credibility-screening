from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch

from services.predictor import LABELS, screen_article


class FakeTokenizer:
    def __call__(self, *args: object, **kwargs: object) -> dict[str, torch.Tensor]:
        return {"input_ids": torch.tensor([[1]])}


class FakeModel:
    def __init__(self, logits: list[list[float]]) -> None:
        self.logits = torch.tensor(logits)

    def __call__(self, **inputs: torch.Tensor) -> SimpleNamespace:
        return SimpleNamespace(logits=self.logits)


class PredictorTests(unittest.TestCase):
    def test_class_zero_is_not_reported_as_factual(self) -> None:
        with patch("services.predictor._load_model", return_value=(FakeTokenizer(), FakeModel([[4.0, 0.0]]))):
            label, _ = screen_article("Example headline", "Example article text")

        self.assertEqual(label, LABELS[0])
        self.assertNotIn("factual", label.lower())
        self.assertIn("unverified", label.lower())

    def test_class_one_still_flags_possible_misinformation(self) -> None:
        with patch("services.predictor._load_model", return_value=(FakeTokenizer(), FakeModel([[0.0, 4.0]]))):
            label, _ = screen_article("Example headline", "Example article text")

        self.assertEqual(label, LABELS[1])
        self.assertIn("fake", label.lower())


if __name__ == "__main__":
    unittest.main()
