"""Ingest company news headlines from the Finnhub free API.

Finnhub's `company-news` endpoint returns recent headlines per ticker. The
free tier requires an API key (set FINNHUB_API_KEY) and limits how far back
you can query, so we default to a short lookback window.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from config import (
    FINNHUB_API_KEY,
    NEWS_LOOKBACK_DAYS,
    REQUEST_DELAY_SECONDS,
)
from src.database import upsert_headlines

logger = logging.getLogger(__name__)

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"


def _epoch_to_iso(epoch_seconds: int) -> str:
    """Convert a Finnhub UNIX timestamp to an ISO datetime string."""
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def fetch_news(symbol: str, lookback_days: int = NEWS_LOOKBACK_DAYS) -> list[dict]:
    """Fetch recent headlines for one symbol from Finnhub.

    Raises RuntimeError if no API key is configured.
    """
    if not FINNHUB_API_KEY:
        raise RuntimeError(
            "FINNHUB_API_KEY is not set. Copy .env.example to .env and add your "
            "free key from https://finnhub.io/."
        )

    end = datetime.utcnow().date()
    start = end - timedelta(days=lookback_days)
    params = {
        "symbol": symbol,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "token": FINNHUB_API_KEY,
    }
    resp = requests.get(FINNHUB_URL, params=params, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    rows: list[dict] = []
    for item in payload:
        headline = (item.get("headline") or "").strip()
        if not headline:
            continue
        rows.append(
            {
                "symbol": symbol,
                "headline": headline,
                "source": item.get("source"),
                "url": item.get("url"),
                "published_at": _epoch_to_iso(item["datetime"]),
            }
        )
    return rows


def ingest_news(symbols: list[str], lookback_days: int = NEWS_LOOKBACK_DAYS) -> int:
    """Fetch and store headlines for every symbol. Returns rows inserted."""
    total_inserted = 0
    for symbol in symbols:
        try:
            rows = fetch_news(symbol, lookback_days)
            inserted = upsert_headlines(rows)
            total_inserted += inserted
            logger.info(
                "%s: %d new headlines (%d fetched)", symbol, inserted, len(rows)
            )
        except Exception as exc:  # keep going even if one ticker fails
            logger.error("Failed to ingest news for %s: %s", symbol, exc)
        time.sleep(REQUEST_DELAY_SECONDS)
    return total_inserted
