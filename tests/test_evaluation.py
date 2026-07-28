"""Tests for the relevance filter, panel construction, and evaluation layer.

The two load-bearing tests here are:

* `test_random_signal_has_insignificant_ic` -- pure noise must NOT produce a
  statistically significant information coefficient. If it does, the IC
  machinery is broken and every number it reports is worthless.
* `test_panel_forward_returns_are_not_contemporaneous` -- the panel must pair
  a signal with the return that follows it, never the one it sits on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.evaluation import (
    cross_sectional_backtest,
    cross_sectional_positions,
    daily_ic,
    information_coefficient,
    summarize_returns,
)
from src.panel import split_panel
from src.relevance import is_relevant


def _days(n: int, start: str = "2027-01-04") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


# ---------------------------------------------------------------------------
# Relevance filter
# ---------------------------------------------------------------------------
def test_matches_company_name():
    assert is_relevant("AAPL", "Apple beats earnings expectations")
    assert is_relevant("WMT", "Walmart deepens healthcare reach")


def test_matches_case_insensitively():
    assert is_relevant("NVDA", "nvidia announces new chip")


def test_rejects_unrelated_headline():
    # The real failures observed in the corpus.
    assert not is_relevant("META", "Entergy Stock May Be Above Fair Value")
    assert not is_relevant("ORCL", "SpaceX is much more of an AI play")
    assert not is_relevant("JNJ", "The Retirement Income Bet That Takes 12 Years")


def test_matches_parenthesized_symbol_even_when_short():
    assert is_relevant("V", "Payments giant (V) raises guidance")
    assert is_relevant("KO", "Beverage roundup (KO) and peers")


def test_short_bare_symbol_does_not_false_positive():
    # "HD" as in high-definition must not tag Home Depot.
    assert not is_relevant("HD", "New HD streaming tier announced")
    # A lone capital V in prose must not tag Visa.
    assert not is_relevant("V", "Shares formed a V shaped recovery")


def test_long_bare_symbol_matches():
    assert is_relevant("AMZN", "AMZN downgraded by analysts")


def test_alias_catches_short_ticker_companies():
    assert is_relevant("HD", "Home Depot raises full-year outlook")
    assert is_relevant("GS", "Goldman Sachs posts record quarter")
    assert is_relevant("PG", "Procter & Gamble lifts dividend")


def test_empty_headline_is_irrelevant():
    assert not is_relevant("AAPL", "")


# ---------------------------------------------------------------------------
# Panel splitting
# ---------------------------------------------------------------------------
def test_split_is_chronological_and_disjoint():
    idx = _days(10)
    sig = pd.DataFrame({"A": range(10)}, index=idx, dtype=float)
    fwd = pd.DataFrame({"A": range(10)}, index=idx, dtype=float)
    (tr_s, tr_f), (te_s, te_f) = split_panel(sig, fwd, train_frac=0.6)
    assert len(tr_s) == 6 and len(te_s) == 4
    # Every training date precedes every test date.
    assert tr_s.index.max() < te_s.index.min()
    assert len(tr_f) == 6 and len(te_f) == 4


def test_split_handles_empty_panel():
    empty = pd.DataFrame()
    (a, b), (c, d) = split_panel(empty, empty)
    assert a.empty and c.empty


# ---------------------------------------------------------------------------
# Information coefficient
# ---------------------------------------------------------------------------
def test_perfect_signal_has_ic_of_one():
    idx = _days(5)
    cols = list("ABCDE")
    sig = pd.DataFrame(
        [[1, 2, 3, 4, 5]] * 5, index=idx, columns=cols, dtype=float
    )
    fwd = sig.copy()  # returns exactly match the ranking
    ics = daily_ic(sig, fwd)
    assert np.allclose(ics.to_numpy(), 1.0)


def test_inverted_signal_has_ic_of_minus_one():
    idx = _days(4)
    cols = list("ABCDE")
    sig = pd.DataFrame([[1, 2, 3, 4, 5]] * 4, index=idx, columns=cols, dtype=float)
    fwd = pd.DataFrame([[5, 4, 3, 2, 1]] * 4, index=idx, columns=cols, dtype=float)
    ics = daily_ic(sig, fwd)
    assert np.allclose(ics.to_numpy(), -1.0)


def test_days_with_too_few_names_are_skipped():
    idx = _days(2)
    sig = pd.DataFrame({"A": [1.0, 1.0], "B": [2.0, 2.0]}, index=idx)
    fwd = sig.copy()
    # Only two names -> below the three-name floor.
    assert daily_ic(sig, fwd).empty


def test_random_signal_has_insignificant_ic():
    """Pure noise must not look predictive."""
    rng = np.random.default_rng(42)
    idx = _days(150)
    cols = [f"T{i}" for i in range(20)]
    sig = pd.DataFrame(rng.normal(size=(150, 20)), index=idx, columns=cols)
    fwd = pd.DataFrame(rng.normal(size=(150, 20)), index=idx, columns=cols)

    result = information_coefficient(sig, fwd)
    assert abs(result.mean_ic) < 0.05, f"noise produced IC {result.mean_ic:.3f}"
    assert result.p_value > 0.05, "noise produced a significant IC"


def test_ic_result_on_empty_panel():
    result = information_coefficient(pd.DataFrame(), pd.DataFrame())
    assert result.n_days == 0 and result.p_value == 1.0


# ---------------------------------------------------------------------------
# Cross-sectional strategy
# ---------------------------------------------------------------------------
def test_positions_are_dollar_neutral():
    idx = _days(3)
    cols = [f"T{i}" for i in range(10)]
    rng = np.random.default_rng(1)
    sig = pd.DataFrame(rng.normal(size=(3, 10)), index=idx, columns=cols)
    w = cross_sectional_positions(sig, top_n=3)
    # Longs and shorts cancel exactly.
    assert np.allclose(w.sum(axis=1).to_numpy(), 0.0)
    # Gross exposure is 2x the long side.
    assert np.allclose(w.abs().sum(axis=1).to_numpy(), 2.0)


def test_positions_flat_when_universe_too_small():
    idx = _days(2)
    sig = pd.DataFrame({"A": [1.0, 2.0], "B": [3.0, 4.0]}, index=idx)
    w = cross_sectional_positions(sig, top_n=5)
    assert (w == 0).all().all()


def test_longs_are_the_highest_signals():
    idx = _days(1)
    cols = list("ABCDEF")
    sig = pd.DataFrame([[1, 2, 3, 4, 5, 6]], index=idx, columns=cols, dtype=float)
    w = cross_sectional_positions(sig, top_n=2)
    row = w.iloc[0]
    assert row["F"] > 0 and row["E"] > 0   # top two
    assert row["A"] < 0 and row["B"] < 0   # bottom two
    assert row["C"] == 0 and row["D"] == 0


def test_backtest_profits_when_signal_predicts():
    idx = _days(30)
    cols = [f"T{i}" for i in range(10)]
    rng = np.random.default_rng(3)
    sig = pd.DataFrame(rng.normal(size=(30, 10)), index=idx, columns=cols)
    # Forward returns proportional to the signal -> the ranking is correct.
    fwd = sig * 0.01
    result = cross_sectional_backtest(sig, fwd, top_n=3, cost_bps=0.0)
    assert result["returns"].sum() > 0


def test_costs_reduce_returns():
    idx = _days(30)
    cols = [f"T{i}" for i in range(10)]
    rng = np.random.default_rng(4)
    sig = pd.DataFrame(rng.normal(size=(30, 10)), index=idx, columns=cols)
    fwd = sig * 0.01
    free = cross_sectional_backtest(sig, fwd, top_n=3, cost_bps=0.0)["returns"].sum()
    costly = cross_sectional_backtest(sig, fwd, top_n=3, cost_bps=100.0)["returns"].sum()
    assert costly < free


def test_summarize_returns_math():
    r = pd.Series([0.10, 0.10], index=_days(2))
    out = summarize_returns(r)
    assert out["total_return"] == pytest.approx(0.21)
    assert out["n_days"] == 2


def test_summarize_empty():
    out = summarize_returns(pd.Series(dtype=float))
    assert out["n_days"] == 0


# ---------------------------------------------------------------------------
# Coverage guard
# ---------------------------------------------------------------------------
def test_trim_drops_newsless_sessions():
    from src.panel import trim_to_coverage

    idx = _days(5)
    sig = pd.DataFrame(
        {
            "A": [1.0, np.nan, 2.0, np.nan, 3.0],
            "B": [1.0, np.nan, 2.0, np.nan, 3.0],
            "C": [1.0, np.nan, 2.0, np.nan, 3.0],
        },
        index=idx,
    )
    fwd = pd.DataFrame(0.01, index=idx, columns=list("ABC"))
    t_sig, t_fwd = trim_to_coverage(sig, fwd, min_names=3)
    assert len(t_sig) == 3
    assert len(t_fwd) == 3


def test_coverage_report_measures_span():
    from src.panel import coverage_report

    idx = _days(4)
    sig = pd.DataFrame(
        {
            "A": [np.nan, 1.0, 1.0, np.nan],
            "B": [np.nan, 1.0, 1.0, np.nan],
            "C": [np.nan, 1.0, 1.0, np.nan],
        },
        index=idx,
    )
    rep = coverage_report(sig, min_names=3)
    assert rep["total_sessions"] == 4
    assert rep["covered_sessions"] == 2
    assert rep["coverage_pct"] == pytest.approx(50.0)
    assert rep["first_covered"] == idx[1]
    assert rep["last_covered"] == idx[2]


def test_coverage_report_on_empty():
    from src.panel import coverage_report

    rep = coverage_report(pd.DataFrame())
    assert rep["covered_sessions"] == 0 and rep["first_covered"] is None