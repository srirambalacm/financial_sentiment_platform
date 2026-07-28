"""Ingest company news headlines from the Finnhub free API.

Why this pages through history
------------------------------
Finnhub's `company-news` endpoint caps each response at roughly 250 items and
returns the *most recent* matches within the requested range. Asking for a
full year in one call therefore does NOT return a year of news -- it returns
~250 headlines clustered in the last few weeks, silently leaving the rest of
the timeline empty.

That failure is invisible in the row counts (you still get thousands of
headlines) but fatal downstream: a backtest whose training window contains no
news will hold nothing and report exactly zero, for every parameter setting.

The fix is to slice the requested range into chunks and issue one request per
chunk, so each window gets its own 250-item budget.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import requests

from config import (
    FINNHUB_API_KEY,
    NEWS_CHUNK_DAYS,
    NEWS_LOOKBACK_DAYS,
    REQUEST_DELAY_SECONDS,
)
from src.database import upsert_headlines

logger = logging.getLogger(__name__)

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"


def _epoch_to_iso(epoch_seconds: int) -> str:
    """Convert a Finnhub UNIX timestamp to an ISO datetime string."""
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


def date_chunks(
    start: date, end: date, chunk_days: int
) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive windows of at most `chunk_days`.

    Windows are inclusive on both ends and never overlap, so a headline is
    requested exactly once. (Duplicates would be harmless anyway -- the
    database deduplicates on a content hash -- but avoiding them saves calls.)
    """
    if chunk_days < 1:
        raise ValueError("chunk_days must be at least 1")
    if end < start:
        return []
    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=chunk_days - 1), end)
        chunks.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return chunks


def _fetch_window(symbol: str, start: date, end: date) -> list[dict]:
    """Fetch one date window of headlines for a symbol."""
    params = {
        "symbol": symbol,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "token": FINNHUB_API_KEY,
    }
    resp = requests.get(FINNHUB_URL, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()

    rows: list[dict] = []
    for item in payload:
        headline = (item.get("headline") or "").strip()
        if not headline or "datetime" not in item:
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


def fetch_news(
    symbol: str,
    lookback_days: int = NEWS_LOOKBACK_DAYS,
    chunk_days: int = NEWS_CHUNK_DAYS,
) -> list[dict]:
    """Fetch headlines for one symbol across the whole lookback window.

    Issues one request per `chunk_days` slice so that each slice gets its own
    result budget instead of the whole range sharing a single 250-item cap.
    """
    if not FINNHUB_API_KEY:
        raise RuntimeError(
            "FINNHUB_API_KEY is not set. Copy .env.example to .env and add your "
            "free key from https://finnhub.io/."
        )

    end = datetime.utcnow().date()
    start = end - timedelta(days=lookback_days)
    windows = date_chunks(start, end, chunk_days)

    rows: list[dict] = []
    for i, (w_start, w_end) in enumerate(windows):
        try:
            batch = _fetch_window(symbol, w_start, w_end)
            rows.extend(batch)
            logger.debug(
                "%s %s..%s: %d headlines", symbol, w_start, w_end, len(batch)
            )
        except Exception as exc:
            logger.warning(
                "%s: window %s..%s failed (%s); continuing.",
                symbol,
                w_start,
                w_end,
                exc,
            )
        # Respect the free tier's rate limit between calls.
        if i < len(windows) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)
    return rows


def ingest_news(
    symbols: list[str],
    lookback_days: int = NEWS_LOOKBACK_DAYS,
    chunk_days: int = NEWS_CHUNK_DAYS,
) -> int:
    """Fetch and store headlines for every symbol. Returns rows inserted."""
    total_inserted = 0
    n_windows = len(
        date_chunks(
            datetime.utcnow().date() - timedelta(days=lookback_days),
            datetime.utcnow().date(),
            chunk_days,
        )
    )
    logger.info(
        "Fetching news in %d windows of <=%d days per ticker (%d requests total).",
        n_windows,
        chunk_days,
        n_windows * len(symbols),
    )

    for symbol in symbols:
        try:
            rows = fetch_news(symbol, lookback_days, chunk_days)
            inserted = upsert_headlines(rows)
            total_inserted += inserted
            logger.info(
                "%s: %d new headlines (%d fetched across %d windows)",
                symbol,
                inserted,
                len(rows),
                n_windows,
            )
        except Exception as exc:
            logger.error("Failed to ingest news for %s: %s", symbol, exc)
        time.sleep(REQUEST_DELAY_SECONDS)
    return total_inserted