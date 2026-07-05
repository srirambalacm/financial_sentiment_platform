"""Tests for the SQLite data-access layer.

These cover the invariants that matter most for data quality: the schema
builds, upserts are idempotent, and both prices and headlines deduplicate
correctly so repeated ingests never double-count.
"""
from __future__ import annotations

import pytest

from src import database as db


@pytest.fixture()
def temp_db(tmp_path):
    """A fresh, initialized database in a temp file for each test."""
    path = tmp_path / "test.db"
    db.init_db(path)
    # Seed one ticker so foreign-key constraints are satisfied.
    db.upsert_tickers([("AAPL", "Apple Inc.", "Technology")], db_path=path)
    return path


def _price_row(date: str, close: float = 100.0) -> dict:
    return {
        "symbol": "AAPL",
        "date": date,
        "open": 99.0,
        "high": 101.0,
        "low": 98.0,
        "close": close,
        "adj_close": close,
        "volume": 1_000_000,
    }


def _headline_row(headline: str, published_at: str = "2027-01-15T12:00:00+00:00") -> dict:
    return {
        "symbol": "AAPL",
        "headline": headline,
        "source": "Reuters",
        "url": "https://example.com/a",
        "published_at": published_at,
    }


# ---------------------------------------------------------------------------
# Schema & tickers
# ---------------------------------------------------------------------------
def test_init_creates_tables(temp_db):
    assert db.count_rows("tickers", temp_db) == 1
    assert db.count_rows("prices", temp_db) == 0
    assert db.count_rows("headlines", temp_db) == 0


def test_upsert_tickers_is_idempotent(temp_db):
    # Re-inserting the same symbol updates rather than duplicates.
    db.upsert_tickers([("AAPL", "Apple (updated)", "Tech")], db_path=temp_db)
    assert db.count_rows("tickers", temp_db) == 1


def test_count_rows_rejects_unknown_table(temp_db):
    with pytest.raises(ValueError):
        db.count_rows("droptable", temp_db)


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------
def test_upsert_prices_inserts(temp_db):
    inserted = db.upsert_prices([_price_row("2027-01-15")], db_path=temp_db)
    assert inserted == 1
    assert db.count_rows("prices", temp_db) == 1


def test_upsert_prices_dedups_on_symbol_date(temp_db):
    db.upsert_prices([_price_row("2027-01-15", close=100.0)], db_path=temp_db)
    # Same (symbol, date) again -> ignored, not double-counted.
    inserted = db.upsert_prices([_price_row("2027-01-15", close=200.0)], db_path=temp_db)
    assert inserted == 0
    assert db.count_rows("prices", temp_db) == 1


def test_get_prices_returns_sorted(temp_db):
    db.upsert_prices(
        [_price_row("2027-01-16"), _price_row("2027-01-15")], db_path=temp_db
    )
    rows = db.get_prices("AAPL", temp_db)
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Headlines
# ---------------------------------------------------------------------------
def test_upsert_headlines_inserts(temp_db):
    inserted = db.upsert_headlines([_headline_row("Apple beats earnings")], db_path=temp_db)
    assert inserted == 1


def test_upsert_headlines_dedups_identical(temp_db):
    db.upsert_headlines([_headline_row("Apple beats earnings")], db_path=temp_db)
    inserted = db.upsert_headlines([_headline_row("Apple beats earnings")], db_path=temp_db)
    assert inserted == 0
    assert db.count_rows("headlines", temp_db) == 1


def test_upsert_headlines_distinguishes_by_time(temp_db):
    # Same text, different publish time -> a distinct headline.
    db.upsert_headlines(
        [_headline_row("Apple news", "2027-01-15T12:00:00+00:00")], db_path=temp_db
    )
    inserted = db.upsert_headlines(
        [_headline_row("Apple news", "2027-01-16T12:00:00+00:00")], db_path=temp_db
    )
    assert inserted == 1
    assert db.count_rows("headlines", temp_db) == 2


def test_sentiment_columns_start_null(temp_db):
    db.upsert_headlines([_headline_row("Apple news")], db_path=temp_db)
    row = db.get_headlines("AAPL", db_path=temp_db)[0]
    assert row["sentiment_label"] is None
    assert row["sentiment_score"] is None
