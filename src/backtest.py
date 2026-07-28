"""Backtest a sentiment-driven strategy against buy-and-hold.

The engine is deliberately simple and transparent — every number it reports
can be recomputed by hand from the returns series. Complexity here buys
nothing except more places for a subtle bug to hide.

Accounting conventions
----------------------
* Returns are simple daily close-to-close returns on adjusted prices.
* **Positions are shifted forward one day before being applied to returns.**
  This is the lookahead guard: the signal computed from day D's news earns
  day D+1's return. Removing the shift inflates results dramatically and is
  the single most common bug in strategy backtests.
* A per-trade cost (in basis points) is charged whenever the position
  changes, so a signal that flips daily is penalized for churn.
* Sharpe assumes a 0% risk-free rate and 252 trading days per year.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


@dataclass
class Performance:
    """Summary statistics for one return stream."""

    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    n_days: int

    def as_dict(self) -> dict:
        return asdict(self)


def compute_returns(prices: pd.Series) -> pd.Series:
    """Simple daily returns from a price series (first day dropped)."""
    if prices.empty:
        return pd.Series(dtype=float)
    return prices.pct_change().dropna()


def equity_curve(returns: pd.Series) -> pd.Series:
    """Cumulative growth of 1 unit of capital."""
    if returns.empty:
        return pd.Series(dtype=float)
    return (1.0 + returns).cumprod()


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough decline of the equity curve (negative number)."""
    if returns.empty:
        return 0.0
    curve = equity_curve(returns)
    running_peak = curve.cummax()
    return float((curve / running_peak - 1.0).min())


def performance_metrics(returns: pd.Series) -> Performance:
    """Compute headline performance statistics for a daily return series."""
    returns = returns.dropna()
    n = len(returns)
    if n == 0:
        return Performance(0.0, 0.0, 0.0, 0.0, 0.0, 0)

    total = float((1.0 + returns).prod() - 1.0)
    # Geometric annualization, so short windows are not wildly overstated
    # by naive multiplication.
    years = n / TRADING_DAYS_PER_YEAR
    annualized = float((1.0 + total) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    std = float(returns.std(ddof=1)) if n > 1 else 0.0
    ann_vol = std * np.sqrt(TRADING_DAYS_PER_YEAR)
    mean = float(returns.mean())
    sharpe = (
        (mean / std) * np.sqrt(TRADING_DAYS_PER_YEAR) if std > 0 else 0.0
    )

    return Performance(
        total_return=total,
        annualized_return=annualized,
        annualized_volatility=float(ann_vol),
        sharpe_ratio=float(sharpe),
        max_drawdown=max_drawdown(returns),
        n_days=n,
    )


def strategy_returns(
    prices: pd.Series,
    positions: pd.Series,
    cost_bps: float = 5.0,
) -> pd.Series:
    """Apply positions to prices with a one-day lag and trading costs.

    `cost_bps` is charged on the absolute change in position, so entering a
    full long position costs `cost_bps` and flipping long-to-short costs twice
    that. Returns the net daily return series of the strategy.
    """
    returns = compute_returns(prices)
    if returns.empty or positions.empty:
        return pd.Series(dtype=float)

    # THE LOOKAHEAD GUARD: day D's signal earns day D+1's return.
    # The shift happens on the positions' own (full) calendar *before*
    # aligning to returns. Aligning first would silently discard the very
    # first session's position, which has no return of its own but is
    # precisely the one that should earn the second session's return.
    lagged = positions.shift(1).reindex(returns.index).fillna(0.0)

    gross = lagged * returns
    turnover = lagged.diff().abs().fillna(lagged.abs())
    costs = turnover * (cost_bps / 10_000.0)
    return (gross - costs).rename("strategy")


def run_backtest(
    prices: pd.Series,
    positions: pd.Series,
    cost_bps: float = 5.0,
) -> dict:
    """Backtest a position series and compare it to buy-and-hold.

    Returns a dict with both performance summaries plus exposure statistics.
    """
    strat = strategy_returns(prices, positions, cost_bps=cost_bps)
    bench = compute_returns(prices)
    # Compare over the identical window.
    bench = bench.reindex(strat.index).dropna()

    # Report exposure on the position actually held (i.e. lagged), so the
    # figure matches what generated the returns above.
    held = positions.shift(1).reindex(bench.index).fillna(0.0)
    exposure = float((held != 0).mean()) if len(held) else 0.0

    return {
        "strategy": performance_metrics(strat),
        "benchmark": performance_metrics(bench),
        "strategy_returns": strat,
        "benchmark_returns": bench,
        "exposure": exposure,
        "n_trades": int((held.diff().abs() > 0).sum()),
    }