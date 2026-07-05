"""Ingest daily OHLCV price data from Yahoo Finance via yfinance.

yfinance requires no API key, which keeps the project frictionless to clone
and run. We download one ticker at a time for a stable, flat column layout
and to make partial failures easy to isolate.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from config import PRICE_LOOKBACK_DAYS, REQUEST_DELAY_SECONDS
from src.database import upsert_prices

logger = logging.getLogger(__name__)


def _dataframe_to_rows(symbol: str, df: pd.DataFrame) -> list[dict]:
    """Convert a yfinance price DataFrame into DB-ready row dicts."""
    rows: list[dict] = []
    for idx, row in df.iterrows():
        rows.append(
            {
                "symbol": symbol,
                "date": pd.Timestamp(idx).date().isoformat(),
                "open": _clean(row.get("Open")),
                "high": _clean(row.get("High")),
                "low": _clean(row.get("Low")),
                "close": _clean(row.get("Close")),
                "adj_close": _clean(row.get("Adj Close", row.get("Close"))),
                "volume": int(row["Volume"]) if pd.notna(row.get("Volume")) else None,
            }
        )
    return rows


def _clean(value) -> float | None:
    """Return a float, or None for missing/NaN values."""
    if value is None or pd.isna(value):
        return None
    return float(value)


def fetch_prices(symbol: str, lookback_days: int = PRICE_LOOKBACK_DAYS) -> list[dict]:
    """Download `lookback_days` of daily bars for one symbol."""
    end = datetime.utcnow().date()
    start = end - timedelta(days=lookback_days)
    df = yf.download(
        symbol,
        start=start.isoformat(),
        end=end.isoformat(),
        progress=False,
        auto_adjust=False,
    )
    if df.empty:
        logger.warning("No price data returned for %s", symbol)
        return []
    # A single-ticker download can still return multi-index columns; flatten.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return _dataframe_to_rows(symbol, df)


def ingest_prices(symbols: list[str], lookback_days: int = PRICE_LOOKBACK_DAYS) -> int:
    """Fetch and store prices for every symbol. Returns rows inserted."""
    total_inserted = 0
    for symbol in symbols:
        try:
            rows = fetch_prices(symbol, lookback_days)
            inserted = upsert_prices(rows)
            total_inserted += inserted
            logger.info("%s: %d new price rows (%d fetched)", symbol, inserted, len(rows))
        except Exception as exc:  # keep going even if one ticker fails
            logger.error("Failed to ingest prices for %s: %s", symbol, exc)
        time.sleep(REQUEST_DELAY_SECONDS)
    return total_inserted
