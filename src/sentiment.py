"""FinBERT-based sentiment scoring for financial text.

We use ProsusAI/finbert, a BERT model fine-tuned on financial communication
text. For each input the model produces probabilities over three classes
(positive / negative / neutral). We summarize each headline with:

    label      : the argmax class (positive | negative | neutral)
    score      : a signed sentiment in [-1, 1], defined as
                 P(positive) - P(negative). Near 0 means neutral/mixed.
    confidence : the probability of the winning class, in [0, 1].

The heavy ML libraries (torch, transformers) are imported lazily inside
`_ensure_loaded`, so this module can be imported and unit-tested without
them installed. The model is loaded once and reused across batches.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ProsusAI/finbert"


class SentimentScorer:
    """A reusable wrapper around FinBERT for batch sentiment scoring."""

    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 32):
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None
        self._tokenizer = None
        self._torch = None
        self._id2label: dict[int, str] = {}

    # -- model loading -----------------------------------------------------
    def _ensure_loaded(self) -> None:
        """Load the tokenizer and model on first use (lazy import)."""
        if self._model is not None:
            return
        import torch  # noqa: WPS433 (intentional lazy import)
        from transformers import (  # noqa: WPS433
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        logger.info("Loading model %s (first call; may download weights)...", self.model_name)
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self._model.eval()
        # Normalize the label mapping to lowercase strings.
        self._id2label = {
            int(i): str(lbl).lower() for i, lbl in self._model.config.id2label.items()
        }
        logger.info("Model loaded. Label map: %s", self._id2label)

    # -- scoring -----------------------------------------------------------
    def _probs_to_result(self, probs: list[float]) -> dict:
        """Convert one probability vector into a {label, score, confidence} dict."""
        # Build a name->prob map so the math doesn't depend on class ordering.
        by_label = {self._id2label[i]: p for i, p in enumerate(probs)}
        winning_idx = max(range(len(probs)), key=lambda i: probs[i])
        return {
            "label": self._id2label[winning_idx],
            "score": float(by_label.get("positive", 0.0) - by_label.get("negative", 0.0)),
            "confidence": float(probs[winning_idx]),
        }

    def score_batch(self, texts: list[str]) -> list[dict]:
        """Score a list of texts. Returns one result dict per input."""
        if not texts:
            return []
        self._ensure_loaded()
        torch = self._torch
        results: list[dict] = []
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start : start + self.batch_size]
            inputs = self._tokenizer(
                chunk,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=256,
            )
            with torch.no_grad():
                logits = self._model(**inputs).logits
                probs = torch.softmax(logits, dim=1).tolist()
            results.extend(self._probs_to_result(p) for p in probs)
        return results


# A module-level default instance so callers can share one loaded model.
_default_scorer: Optional[SentimentScorer] = None


def get_scorer() -> SentimentScorer:
    """Return a shared SentimentScorer instance (loads the model once)."""
    global _default_scorer
    if _default_scorer is None:
        _default_scorer = SentimentScorer()
    return _default_scorer