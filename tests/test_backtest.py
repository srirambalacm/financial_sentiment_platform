"""Tests for the Phase 3 signal + backtest layer.

The most important test here is `test_no_lookahead_bias`: it builds a world
where sentiment perfectly predicts the *same day's* return. An engine that
leaks future information would post enormous profits on that data; a correct
one earns nothing, because by the time it can trade, the move has happened.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest import (
    compute_returns,
    equity_curve,
    max_drawdown,
    performance_metrics,
    run_backtest,
    strategy_returns,
)
from src.signals import (
    map_to_trading_days,
    positions_from_signal,
    rolling_signal,
)


def _days(n: int, start: str = "2027-01-04") -> pd.DatetimeIndex:
    """n consecutive weekday sessions."""
    return pd.bdate_range(start=start, periods=n)


# ---------------------------------------------------------------------------
# Signal construction
# ---------------------------------------------------------------------------
def test_weekend_news_maps_to_next_session():
    sessions = pd.DatetimeIndex(["2027-01-08", "2027-01-11"])  # Fri, Mon
    news = pd.DataFrame(
        {"avg_score": [0.5], "n_headlines": [3]},
        index=pd.DatetimeIndex(["2027-01-09"]),  # Saturday
    )
    daily = map_to_trading_days(news, sessions)
    # Saturday news must land on Monday, never back on Friday.
    assert pd.isna(daily.loc[pd.Timestamp("2027-01-08")])
    assert daily.loc[pd.Timestamp("2027-01-11")] == pytest.approx(0.5)


def test_same_day_news_stays_on_that_session():
    sessions = pd.DatetimeIndex(["2027-01-08", "2027-01-11"])
    news = pd.DataFrame(
        {"avg_score": [0.4], "n_headlines": [2]},
        index=pd.DatetimeIndex(["2027-01-08"]),
    )
    daily = map_to_trading_days(news, sessions)
    assert daily.loc[pd.Timestamp("2027-01-08")] == pytest.approx(0.4)


def test_combined_days_use_count_weighted_mean():
    sessions = pd.DatetimeIndex(["2027-01-11"])  # Monday only
    news = pd.DataFrame(
        {"avg_score": [1.0, 0.0], "n_headlines": [9, 1]},
        index=pd.DatetimeIndex(["2027-01-09", "2027-01-10"]),  # Sat, Sun
    )
    daily = map_to_trading_days(news, sessions)
    # (1.0*9 + 0.0*1) / 10 == 0.9, not the unweighted 0.5.
    assert daily.loc[pd.Timestamp("2027-01-11")] == pytest.approx(0.9)


def test_news_after_last_session_is_dropped():
    sessions = pd.DatetimeIndex(["2027-01-08"])
    news = pd.DataFrame(
        {"avg_score": [0.9], "n_headlines": [5]},
        index=pd.DatetimeIndex(["2027-02-01"]),
    )
    daily = map_to_trading_days(news, sessions)
    assert daily.dropna().empty


def test_rolling_signal_smooths():
    idx = _days(3)
    daily = pd.Series([0.9, 0.0, 0.0], index=idx)
    sig = rolling_signal(daily, window=3)
    assert sig.iloc[0] == pytest.approx(0.9)          # min_periods=1
    assert sig.iloc[2] == pytest.approx(0.3)          # mean of the three


def test_positions_long_only_by_default():
    idx = _days(3)
    sig = pd.Series([0.5, -0.5, np.nan], index=idx)
    pos = positions_from_signal(sig, threshold=0.1)
    assert list(pos) == [1.0, 0.0, 0.0]               # no shorting, NaN flat


def test_positions_can_short_when_enabled():
    idx = _days(2)
    sig = pd.Series([0.5, -0.5], index=idx)
    pos = positions_from_signal(sig, threshold=0.1, allow_short=True)
    assert list(pos) == [1.0, -1.0]


# ---------------------------------------------------------------------------
# Backtest math
# ---------------------------------------------------------------------------
def test_compute_returns_basic():
    prices = pd.Series([100.0, 110.0, 99.0], index=_days(3))
    r = compute_returns(prices)
    assert r.iloc[0] == pytest.approx(0.10)
    assert r.iloc[1] == pytest.approx(-0.10)


def test_equity_curve_compounds():
    r = pd.Series([0.10, 0.10], index=_days(2))
    assert equity_curve(r).iloc[-1] == pytest.approx(1.21)


def test_max_drawdown_is_negative_peak_to_trough():
    r = pd.Series([0.50, -0.50], index=_days(2))
    # 1.0 -> 1.5 -> 0.75, a 50% drawdown from the peak.
    assert max_drawdown(r) == pytest.approx(-0.50)


def test_performance_metrics_on_empty():
    m = performance_metrics(pd.Series(dtype=float))
    assert m.n_days == 0 and m.total_return == 0.0


def test_positions_are_lagged_one_day():
    idx = _days(3)
    prices = pd.Series([100.0, 110.0, 121.0], index=idx)
    # Long from the very first session.
    positions = pd.Series([1.0, 1.0, 1.0], index=idx)
    strat = strategy_returns(prices, positions, cost_bps=0.0)
    # Returns exist for sessions 2 and 3. The position from session 1 earns
    # session 2's return, so both are captured.
    assert len(strat) == 2
    assert strat.iloc[0] == pytest.approx(0.10)


def test_no_lookahead_bias():
    """Sentiment that predicts the SAME day's move must earn nothing."""
    n = 60
    idx = _days(n)
    rng = np.random.default_rng(0)
    daily_moves = rng.choice([-0.02, 0.02], size=n - 1)

    prices = [100.0]
    for m in daily_moves:
        prices.append(prices[-1] * (1.0 + m))
    price_series = pd.Series(prices, index=idx)

    # An oracle signal: on the session *before* each move we know nothing,
    # but on the session the move happens we "already know" it was up.
    # Position is set on the same day as the return it predicts.
    positions = pd.Series(0.0, index=idx)
    positions.iloc[1:] = np.where(daily_moves > 0, 1.0, 0.0)

    strat = strategy_returns(price_series, positions, cost_bps=0.0)
    total = float((1.0 + strat).prod() - 1.0)

    # With the one-day lag, yesterday's "knowledge" of yesterday's move is
    # useless for today, so the result must not look like a money printer.
    # A leaking engine would compound +2% on nearly every up day.
    assert total < 0.50, f"suspiciously high return {total:.2%} suggests leakage"


def test_run_backtest_reports_both_streams():
    idx = _days(10)
    prices = pd.Series(np.linspace(100, 120, 10), index=idx)
    positions = pd.Series(1.0, index=idx)
    result = run_backtest(prices, positions, cost_bps=0.0)
    assert result["strategy"].n_days == result["benchmark"].n_days
    assert result["exposure"] == pytest.approx(1.0)
    # Fully invested the whole time should track buy-and-hold closely.
    assert result["strategy"].total_return == pytest.approx(
        result["benchmark"].total_return, abs=1e-9
    )


def test_flat_strategy_earns_zero():
    idx = _days(10)
    prices = pd.Series(np.linspace(100, 120, 10), index=idx)
    positions = pd.Series(0.0, index=idx)
    result = run_backtest(prices, positions, cost_bps=0.0)
    assert result["strategy"].total_return == pytest.approx(0.0)
    assert result["exposure"] == pytest.approx(0.0)


def test_trading_costs_reduce_returns():
    idx = _days(10)
    prices = pd.Series(np.linspace(100, 120, 10), index=idx)
    positions = pd.Series(1.0, index=idx)
    free = run_backtest(prices, positions, cost_bps=0.0)["strategy"].total_return
    costly = run_backtest(prices, positions, cost_bps=50.0)["strategy"].total_return
    assert costly < free