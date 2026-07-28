"""Build the cross-sectional panel: a date x ticker grid of signals and returns.

Per-ticker backtests answer "does sentiment help for AAPL?" one name at a
time. The panel view instead asks "on any given day, does the *relative*
ranking of sentiment across the universe predict relative returns?" That is
how equity signals are actually evaluated and traded, and it sidesteps the
scale problem that sinks absolute thresholds: a fixed cutoff like +0.10 is
simultaneously too high for a densely covered mega-cap (whose daily average
concentrates near the corpus mean) and too low for a thinly covered name.
"""
from __future__ import annotations

import pandas as pd

from src.signals import (
    load_daily_sentiment,
    load_price_series,
    map_to_trading_days,
    rolling_signal,
)
from src.tickers import symbols


def build_panel(
    window: int = 3,
    relevant_only: bool = False,
    db_path=None,
    universe: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (signals, forward_returns) as aligned date x ticker frames.

    `forward_returns.loc[d, t]` is the return earned *after* day d — that is,
    the return from d to the next session. Pairing it with `signals.loc[d, t]`
    therefore compares a signal against a return that had not yet happened
    when the signal was known, which is the lookahead guard in panel form.
    """
    universe = universe or symbols()
    signal_cols: dict[str, pd.Series] = {}
    fwd_cols: dict[str, pd.Series] = {}

    for symbol in universe:
        prices = load_price_series(symbol, db_path)
        if prices.empty or len(prices) < 2:
            continue

        sentiment = load_daily_sentiment(
            symbol, db_path, relevant_only=relevant_only
        )
        daily = map_to_trading_days(sentiment, prices.index)
        signal = rolling_signal(daily, window=window)

        returns = prices.pct_change()
        # Shift returns backwards so row d holds the NEXT session's return.
        forward = returns.shift(-1)

        signal_cols[symbol] = signal
        fwd_cols[symbol] = forward

    if not signal_cols:
        return pd.DataFrame(), pd.DataFrame()

    signals = pd.DataFrame(signal_cols).sort_index()
    forwards = pd.DataFrame(fwd_cols).sort_index()
    # Align on the shared calendar.
    common = signals.index.intersection(forwards.index)
    return signals.loc[common], forwards.loc[common]


def trim_to_coverage(
    signals: pd.DataFrame, forwards: pd.DataFrame, min_names: int = 3
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drop sessions where too few tickers carry a signal.

    A date with no news anywhere in the universe contributes nothing but a
    row of zeros, which silently drags every statistic toward zero and — far
    worse — makes a train/test split look valid when the training half is
    entirely newsless. Trimming to the genuinely covered window makes the
    real sample size visible.
    """
    if signals.empty:
        return signals, forwards
    counts = signals.notna().sum(axis=1)
    keep = counts[counts >= min_names].index
    return signals.loc[keep], forwards.loc[keep]


def coverage_report(signals: pd.DataFrame, min_names: int = 3) -> dict:
    """Summarize how much of the price calendar actually has news behind it."""
    if signals.empty:
        return {
            "total_sessions": 0,
            "covered_sessions": 0,
            "coverage_pct": 0.0,
            "first_covered": None,
            "last_covered": None,
        }
    counts = signals.notna().sum(axis=1)
    covered = counts[counts >= min_names]
    return {
        "total_sessions": int(len(signals)),
        "covered_sessions": int(len(covered)),
        "coverage_pct": float(len(covered) / len(signals) * 100.0),
        "first_covered": covered.index.min() if len(covered) else None,
        "last_covered": covered.index.max() if len(covered) else None,
    }


def split_panel(
    signals: pd.DataFrame, forwards: pd.DataFrame, train_frac: float = 0.6
) -> tuple[tuple[pd.DataFrame, pd.DataFrame], tuple[pd.DataFrame, pd.DataFrame]]:
    """Chronologically split a panel into (train, test) halves.

    The split is by date, never random: shuffling time series rows would let
    the model learn from the future, which is the subtler cousin of lookahead
    bias and just as fatal.
    """
    n = len(signals)
    if n == 0:
        return (signals, forwards), (signals, forwards)
    cut = max(1, int(n * train_frac))
    train = (signals.iloc[:cut], forwards.iloc[:cut])
    test = (signals.iloc[cut:], forwards.iloc[cut:])
    return train, test