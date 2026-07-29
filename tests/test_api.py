"""Tests for the FinSent HTTP API.

A temporary database is seeded once per module and the app is pointed at it,
so these run in about a second and never touch the real corpus. The point is
to verify the contract — status codes, response shapes, validation, and the
cache — not to re-test the analysis maths, which `test_evaluation.py` and
`test_backtest.py` already cover.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def client():
    """A TestClient wired to a small seeded database.

    Because `src.database.get_connection` resolves DB_PATH at call time,
    redirecting the whole application at a temp database is a single
    assignment — no module reloading or import-order juggling required.
    """
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "api_test.db")

    from src import database

    database.DB_PATH = db_path

    from src.database import (
        get_unscored_headlines,
        init_db,
        update_relevance,
        update_sentiment,
        upsert_headlines,
        upsert_prices,
        upsert_tickers,
    )
    from src.tickers import UNIVERSE

    init_db(db_path)
    upsert_tickers(
        [(t.symbol, t.name, t.sector) for t in UNIVERSE], db_path=db_path
    )

    rng = np.random.default_rng(0)
    days = pd.bdate_range("2027-01-04", periods=40)

    for t in UNIVERSE:
        price = 100.0
        rows = []
        for d in days:
            price *= 1 + rng.normal(0.0005, 0.012)
            rows.append(
                {
                    "symbol": t.symbol,
                    "date": d.date().isoformat(),
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "adj_close": price,
                    "volume": 1_000,
                }
            )
        upsert_prices(rows, db_path=db_path)

    headlines = []
    for t in UNIVERSE:
        first = t.name.split()[0]
        for d in days:
            for k in range(2):
                headlines.append(
                    {
                        "symbol": t.symbol,
                        "headline": f"{first} reports update {d.date()} #{k}",
                        "source": "TestWire",
                        "url": "https://example.com/a",
                        "published_at": d.isoformat() + "T13:00:00+00:00",
                    }
                )
    upsert_headlines(headlines, db_path=db_path)

    unscored = get_unscored_headlines(db_path=db_path)
    updates, relevance = [], []
    for row in unscored:
        score = float(np.clip(rng.normal(0.05, 0.45), -1, 1))
        label = (
            "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
        )
        updates.append((label, score, 0.8, row["id"]))
        relevance.append((1, row["id"]))
    update_sentiment(updates, db_path=db_path)
    update_relevance(relevance, db_path=db_path)

    from fastapi.testclient import TestClient

    from api.main import app, cache

    cache.clear()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------
def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_benchmark_reports_recorded_metrics(client):
    resp = client.get("/api/benchmark")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"] == "ProsusAI/finbert"
    assert 0.9 < body["accuracy"] < 1.0
    assert 0.9 < body["macro_f1"] < 1.0


def test_openapi_schema_is_generated(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/evaluation" in resp.json()["paths"]


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------
def test_tickers_returns_full_universe(client):
    resp = client.get("/api/tickers")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 25
    assert {"symbol", "name", "sector", "headline_count"} <= set(body[0])
    assert body[0]["headline_count"] > 0


def test_stats_are_internally_consistent(client):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_tickers"] == 25
    assert body["n_scored"] <= body["n_headlines"]
    total_in_distribution = sum(d["count"] for d in body["distribution"])
    assert total_in_distribution == body["n_scored"]


def test_timeseries_shape_and_alignment(client):
    resp = client.get("/api/tickers/AAPL/timeseries?days=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["n_sessions"] == len(body["points"]) == 10
    point = body["points"][0]
    assert {"date", "close", "sentiment", "headline_count"} <= set(point)
    assert point["close"] > 0


def test_timeseries_accepts_lowercase_symbol(client):
    assert client.get("/api/tickers/aapl/timeseries?days=5").status_code == 200


def test_unknown_ticker_returns_404(client):
    resp = client.get("/api/tickers/NOTREAL/timeseries")
    assert resp.status_code == 404
    assert "Unknown ticker" in resp.json()["detail"]


def test_timeseries_rejects_invalid_days(client):
    assert client.get("/api/tickers/AAPL/timeseries?days=0").status_code == 422
    assert client.get("/api/tickers/AAPL/timeseries?days=99999").status_code == 422


def test_headlines_respect_limit_and_ordering(client):
    resp = client.get("/api/tickers/MSFT/headlines?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 5
    dates = [h["published_at"] for h in body]
    assert dates == sorted(dates, reverse=True)   # newest first
    assert body[0]["sentiment_label"] in {"positive", "negative", "neutral"}


def test_headlines_limit_is_bounded(client):
    assert client.get("/api/tickers/MSFT/headlines?limit=0").status_code == 422
    assert client.get("/api/tickers/MSFT/headlines?limit=9999").status_code == 422


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def test_evaluation_returns_full_payload(client):
    resp = client.get("/api/evaluation")
    assert resp.status_code == 200
    body = resp.json()
    assert {"coverage", "ic_full_sample", "ic_out_of_sample", "performance"} <= set(body)
    assert len(body["performance"]) == 3
    assert body["verdict"]


def test_evaluation_ic_fields_are_well_formed(client):
    body = client.get("/api/evaluation").json()
    ic = body["ic_full_sample"]
    assert -1.0 <= ic["mean_ic"] <= 1.0
    assert 0.0 <= ic["p_value"] <= 1.0
    assert isinstance(ic["significant"], bool)
    assert ic["significant"] == (ic["p_value"] < 0.05)


def test_evaluation_rejects_out_of_range_params(client):
    assert client.get("/api/evaluation?train_frac=1.5").status_code == 422
    assert client.get("/api/evaluation?cost_bps=-5").status_code == 422


def test_evaluation_is_cached(client):
    """A second identical request must be served from cache, not recomputed."""
    from api.main import cache

    cache.clear()
    client.get("/api/evaluation")
    before = cache.stats()["entries"]
    client.get("/api/evaluation")
    after = cache.stats()["entries"]
    assert before == after   # no new entry -> the second call was a cache hit


def test_cache_endpoint_reports_entries(client):
    resp = client.get("/api/cache")
    assert resp.status_code == 200
    assert "entries" in resp.json()