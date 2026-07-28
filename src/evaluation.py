"""Evaluate the sentiment signal the way a quant would.

Two measurements, deliberately separate:

`information_coefficient`
    The rank correlation between today's signal and tomorrow's return,
    computed cross-sectionally (within each day) and then averaged. This asks
    the raw question -- does the signal contain *any* predictive information?
    -- without entangling it with position sizing, costs, or thresholds.
    Real equity signals live around an IC of 0.02-0.05; anything above ~0.10
    on a simple public dataset should be treated as a bug until proven
    otherwise.

`cross_sectional_backtest`
    Each day, go long the top-N names by signal and short the bottom-N,
    equal-weighted. This is dollar-neutral, so it strips out the market
    return that dominates a long-only strategy and isolates whether the
    *ranking* carries information. It also needs no absolute threshold, which
    is what broke the per-ticker version.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


@dataclass
class ICResult:
    """Information-coefficient summary."""

    mean_ic: float
    std_ic: float
    t_stat: float
    p_value: float
    n_days: int
    hit_rate: float  # share of days with positive IC

    def as_dict(self) -> dict:
        return {
            "mean_ic": self.mean_ic,
            "std_ic": self.std_ic,
            "t_stat": self.t_stat,
            "p_value": self.p_value,
            "n_days": self.n_days,
            "hit_rate": self.hit_rate,
        }


def daily_ic(
    signals: pd.DataFrame, forwards: pd.DataFrame, method: str = "spearman"
) -> pd.Series:
    """Cross-sectional correlation of signal vs next-day return, per day.

    Days with fewer than three names having both a signal and a return are
    skipped: a correlation over two points is either +1 or -1 and carries no
    information.
    """
    ics: dict[pd.Timestamp, float] = {}
    for date in signals.index:
        s = signals.loc[date]
        f = forwards.loc[date] if date in forwards.index else None
        if f is None:
            continue
        pair = pd.DataFrame({"s": s, "f": f}).dropna()
        if len(pair) < 3 or pair["s"].nunique() < 2:
            continue
        ic = pair["s"].corr(pair["f"], method=method)
        if pd.notna(ic):
            ics[date] = float(ic)
    return pd.Series(ics, name="ic").sort_index()


def information_coefficient(
    signals: pd.DataFrame, forwards: pd.DataFrame, method: str = "spearman"
) -> ICResult:
    """Summarize the daily IC series with a t-test against zero."""
    from scipy import stats

    ics = daily_ic(signals, forwards, method=method)
    n = len(ics)
    if n < 2:
        return ICResult(0.0, 0.0, 0.0, 1.0, n, 0.0)

    mean = float(ics.mean())
    std = float(ics.std(ddof=1))
    t_stat, p_value = stats.ttest_1samp(ics.to_numpy(), 0.0)
    return ICResult(
        mean_ic=mean,
        std_ic=std,
        t_stat=float(t_stat),
        p_value=float(p_value),
        n_days=n,
        hit_rate=float((ics > 0).mean()),
    )


def cross_sectional_positions(
    signals: pd.DataFrame, top_n: int = 5
) -> pd.DataFrame:
    """Build dollar-neutral long/short weights from daily signal ranks.

    Each day the top `top_n` names by signal get +1/top_n and the bottom
    `top_n` get -1/top_n, so the book is fully invested, equally weighted,
    and nets to zero exposure. Days with too few signalled names are flat.
    """
    weights = pd.DataFrame(0.0, index=signals.index, columns=signals.columns)
    for date in signals.index:
        row = signals.loc[date].dropna()
        if len(row) < 2 * top_n:
            continue
        ranked = row.sort_values(ascending=False)
        longs = ranked.index[:top_n]
        shorts = ranked.index[-top_n:]
        weights.loc[date, longs] = 1.0 / top_n
        weights.loc[date, shorts] = -1.0 / top_n
    return weights


def cross_sectional_backtest(
    signals: pd.DataFrame,
    forwards: pd.DataFrame,
    top_n: int = 5,
    cost_bps: float = 5.0,
) -> dict:
    """Backtest the top-N / bottom-N long-short book.

    Weights formed from day d's signal are applied to day d's *forward*
    return, i.e. the move that happens after d. No same-day information is
    ever used.
    """
    weights = cross_sectional_positions(signals, top_n=top_n)
    aligned_fwd = forwards.reindex_like(weights)

    gross = (weights * aligned_fwd).sum(axis=1, min_count=1)

    turnover = weights.diff().abs().sum(axis=1)
    turnover.iloc[0] = weights.iloc[0].abs().sum() if len(weights) else 0.0
    costs = turnover * (cost_bps / 10_000.0)

    net = (gross - costs).dropna()
    return {
        "returns": net,
        "gross_returns": gross.dropna(),
        "turnover": turnover,
        "weights": weights,
    }


def summarize_returns(returns: pd.Series) -> dict:
    """Headline statistics for a daily return stream."""
    returns = returns.dropna()
    n = len(returns)
    if n == 0:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "n_days": 0,
        }

    total = float((1.0 + returns).prod() - 1.0)
    years = n / TRADING_DAYS_PER_YEAR
    ann = float((1.0 + total) ** (1.0 / years) - 1.0) if years > 0 and total > -1 else 0.0
    std = float(returns.std(ddof=1)) if n > 1 else 0.0
    sharpe = float(returns.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR)) if std > 0 else 0.0
    curve = (1.0 + returns).cumprod()
    mdd = float((curve / curve.cummax() - 1.0).min())

    return {
        "total_return": total,
        "annualized_return": ann,
        "annualized_volatility": std * float(np.sqrt(TRADING_DAYS_PER_YEAR)),
        "sharpe_ratio": sharpe,
        "max_drawdown": mdd,
        "n_days": n,
    }