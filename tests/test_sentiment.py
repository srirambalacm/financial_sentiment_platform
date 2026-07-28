"""Tests for the Phase 2 sentiment layer.

Covers the DB write-back path (fetch unscored -> update) and the pure scoring
math in SentimentScorer. The math is tested without loading FinBERT by
injecting a label map and calling the probability-to-result helper directly,
so these tests run fast and need no torch/transformers install.
"""
from __future__ import annotations

import pytest

from src import database as db
from src.sentiment import SentimentScorer


@pytest.fixture()
def temp_db(tmp_path):
    path = tmp_path / "test.db"
    db.init_db(path)
    db.upsert_tickers([("AAPL", "Apple Inc.", "Technology")], db_path=path)
    db.upsert_headlines(
        [
            {
                "symbol": "AAPL",
                "headline": "Apple crushes earnings expectations",
                "source": "Reuters",
                "url": "https://example.com/1",
                "published_at": "2027-01-15T12:00:00+00:00",
            },
            {
                "symbol": "AAPL",
                "headline": "Apple faces antitrust probe",
                "source": "Bloomberg",
                "url": "https://example.com/2",
                "published_at": "2027-01-16T12:00:00+00:00",
            },
        ],
        db_path=path,
    )
    return path


# ---------------------------------------------------------------------------
# DB write-back path
# ---------------------------------------------------------------------------
def test_unscored_headlines_start_as_all(temp_db):
    unscored = db.get_unscored_headlines(db_path=temp_db)
    assert len(unscored) == 2


def test_update_sentiment_marks_rows_scored(temp_db):
    unscored = db.get_unscored_headlines(db_path=temp_db)
    updates = [("positive", 0.8, 0.91, unscored[0]["id"])]
    written = db.update_sentiment(updates, db_path=temp_db)
    assert written == 1
    # Only one row left unscored now.
    assert len(db.get_unscored_headlines(db_path=temp_db)) == 1


def test_scored_values_persist(temp_db):
    row = db.get_unscored_headlines(db_path=temp_db)[0]
    db.update_sentiment([("negative", -0.6, 0.77, row["id"])], db_path=temp_db)
    stored = db.get_headlines("AAPL", db_path=temp_db)
    match = [r for r in stored if r["id"] == row["id"]][0]
    assert match["sentiment_label"] == "negative"
    assert match["sentiment_score"] == pytest.approx(-0.6)
    assert match["sentiment_confidence"] == pytest.approx(0.77)


def test_limit_respected(temp_db):
    assert len(db.get_unscored_headlines(limit=1, db_path=temp_db)) == 1


# ---------------------------------------------------------------------------
# Scoring math (no model load required)
# ---------------------------------------------------------------------------
def _scorer_with_labels() -> SentimentScorer:
    s = SentimentScorer()
    # Inject the ProsusAI/finbert label order without loading the model.
    s._id2label = {0: "positive", 1: "negative", 2: "neutral"}
    return s


def test_positive_dominant_probs():
    s = _scorer_with_labels()
    res = s._probs_to_result([0.9, 0.05, 0.05])
    assert res["label"] == "positive"
    assert res["score"] == pytest.approx(0.85)   # 0.9 - 0.05
    assert res["confidence"] == pytest.approx(0.9)


def test_negative_dominant_probs():
    s = _scorer_with_labels()
    res = s._probs_to_result([0.1, 0.8, 0.1])
    assert res["label"] == "negative"
    assert res["score"] == pytest.approx(-0.7)   # 0.1 - 0.8
    assert res["confidence"] == pytest.approx(0.8)


def test_neutral_probs_score_near_zero():
    s = _scorer_with_labels()
    res = s._probs_to_result([0.2, 0.2, 0.6])
    assert res["label"] == "neutral"
    assert res["score"] == pytest.approx(0.0)
    assert res["confidence"] == pytest.approx(0.6)


def test_empty_batch_returns_empty():
    s = _scorer_with_labels()
    assert s.score_batch([]) == []