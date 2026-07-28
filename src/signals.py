"""Turn scored headlines into a daily trading signal.

The pipeline, per ticker:

    headlines (timestamped, scored)
        -> daily mean sentiment, weighted by headline count
        -> mapped onto trading days (weekend news rolls to the next session)
        -> rolling N-day mean  (smooths single-day noise)
        -> position: long when the rolling mean clears a threshold

Avoiding lookahead bias
-----------------------
Two rules keep this honest, and they matter more than any other detail here:

1. News published on calendar day D is assigned to the *next trading session
   at or after D*. Saturday news counts for Monday, never for Friday.
2. The position derived from day D's signal is applied to day D+1's return
   (see `backtest.py`, where positions are shifted forward one day). We never
   trade on information that would not have been available before the bar.

Without rule 2 a backtest looks spectacular and means nothing, because the
strategy is effectively reading the newspaper a day early.
"""
from __future__ import annotations

import pandas as pd

from src.database import get_prices, get_sentiment_by_date


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_price_series(symbol: str, db_path=None) -> pd.Series:
    """Return an adjusted-close price series indexed by date (ascending)."""
    rows = get_prices(symbol, db_path) if db_path else get_prices(symbol)
    if not rows:
        return pd.Series(dtype=float)
    dates, closes = [], []
    for r in rows:
        price = r["adj_close"] if r["adj_close"] is not None else r["close"]
        if price is None:
            continue
        dates.append(pd.Timestamp(r["date"]))
        closes.append(float(price))
    return pd.Series(closes, index=pd.DatetimeIndex(dates), name=symbol).sort_index()


def load_daily_sentiment(
    symbol: str, db_path=None, relevant_only: bool = False
) -> pd.DataFrame:
    """Return a DataFrame of (avg_score, n_headlines) indexed by news date.

    With `relevant_only`, only headlines that passed the relevance filter are
    aggregated (see src/relevance.py).
    """
    rows = (
        get_sentiment_by_date(symbol, db_path, relevant_only=relevant_only)
        if db_path
        else get_sentiment_by_date(symbol, relevant_only=relevant_only)
    )
    if not rows:
        return pd.DataFrame(columns=["avg_score", "n_headlines"])
    df = pd.DataFrame(
        {
            "avg_score": [float(r["avg_score"]) for r in rows],
            "n_headlines": [int(r["n_headlines"]) for r in rows],
        },
        index=pd.DatetimeIndex([pd.Timestamp(r["date"]) for r in rows]),
    )
    return df.sort_index()


# ---------------------------------------------------------------------------
# Signal construction
# ---------------------------------------------------------------------------
def map_to_trading_days(
    sentiment: pd.DataFrame, trading_days: pd.DatetimeIndex
) -> pd.Series:
    """Collapse dated sentiment onto trading sessions.

    Each news date is assigned to the first trading day at or after it, so
    weekend and holiday news lands on the next open session. When several
    news dates map to one session, their scores are combined as a mean
    weighted by headline count (so a 40-headline day outweighs a 2-headline
    day rather than counting equally).

    News dated after the final trading day is dropped: there is no session
    left to trade it in.
    """
    if sentiment.empty or len(trading_days) == 0:
        return pd.Series(dtype=float)

    trading_days = pd.DatetimeIndex(sorted(trading_days))
    # searchsorted(side="left") gives the first session >= the news date.
    positions = trading_days.searchsorted(sentiment.index, side="left")

    frame = sentiment.copy()
    frame["session_idx"] = positions
    # Drop news that falls after the last available session.
    frame = frame[frame["session_idx"] < len(trading_days)]
    if frame.empty:
        return pd.Series(dtype=float)

    frame["session"] = trading_days[frame["session_idx"].to_numpy()]
    frame["weighted"] = frame["avg_score"] * frame["n_headlines"]

    grouped = frame.groupby("session").agg(
        weighted_sum=("weighted", "sum"), total_n=("n_headlines", "sum")
    )
    daily = grouped["weighted_sum"] / grouped["total_n"]
    daily.name = "daily_sentiment"
    # Reindex onto the full session calendar; sessions without news stay NaN.
    return daily.reindex(trading_days)


def rolling_signal(daily_sentiment: pd.Series, window: int = 3) -> pd.Series:
    """Smooth daily sentiment with a trailing rolling mean.

    `min_periods=1` means a session still gets a signal when only part of the
    window has news, which matters because coverage is uneven. Sessions with
    no news anywhere in the window remain NaN and are treated as flat.
    """
    if daily_sentiment.empty:
        return daily_sentiment
    signal = daily_sentiment.rolling(window=window, min_periods=1).mean()
    signal.name = "signal"
    return signal


def positions_from_signal(
    signal: pd.Series, threshold: float = 0.1, allow_short: bool = False
) -> pd.Series:
    """Convert a signal into daily target positions.

    Long-only by default: +1 when the signal clears `threshold`, else flat.
    With `allow_short`, the strategy also goes -1 below the negative
    threshold. NaN (no news in the window) is always flat.
    """
    if signal.empty:
        return signal
    pos = pd.Series(0.0, index=signal.index, name="position")
    pos[signal > threshold] = 1.0
    if allow_short:
        pos[signal < -threshold] = -1.0
    pos[signal.isna()] = 0.0
    return pos


def build_positions(
    symbol: str,
    window: int = 3,
    threshold: float = 0.1,
    allow_short: bool = False,
    db_path=None,
    relevant_only: bool = False,
) -> tuple[pd.Series, pd.Series]:
    """Full signal pipeline for one symbol.

    Returns (prices, positions) aligned on the same trading-day index.
    """
    prices = load_price_series(symbol, db_path)
    if prices.empty:
        return prices, pd.Series(dtype=float)
    sentiment = load_daily_sentiment(symbol, db_path, relevant_only=relevant_only)
    daily = map_to_trading_days(sentiment, prices.index)
    signal = rolling_signal(daily, window=window)
    positions = positions_from_signal(signal, threshold, allow_short)
    return prices, positions