"""Service layer: turns the analysis modules into API-shaped responses.

Routes stay thin and this module holds the logic, so the querying and
assembly can be tested without spinning up HTTP, and so the same functions
could be reused by a CLI or a scheduled job later.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from src.database import get_connection, count_rows
from src.evaluation import (
    cross_sectional_backtest,
    information_coefficient,
    summarize_returns,
)
from src.panel import build_panel, coverage_report, split_panel, trim_to_coverage
from src.signals import load_daily_sentiment, load_price_series, map_to_trading_days
from src.tickers import UNIVERSE

# Benchmark figures recorded from scripts/benchmark_model.py. Stored as a
# constant rather than recomputed on request: re-running the benchmark means
# 3,453 transformer inferences, which is not something an HTTP handler should
# ever do.
BENCHMARK = {
    "model": "ProsusAI/finbert",
    "dataset": "Financial PhraseBank",
    "subset": "sentences_75agree",
    "n_sentences": 3453,
    "accuracy": 0.9473,
    "macro_f1": 0.9365,
}

WINDOW_GRID = [1, 2, 3, 5, 10]
TOP_N_GRID = [3, 5, 7]


def _safe_float(value) -> float:
    """Convert to float, mapping NaN/inf to 0.0 so JSON stays valid."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0


# ---------------------------------------------------------------------------
# Tickers
# ---------------------------------------------------------------------------
def list_tickers() -> list[dict]:
    """Return the universe with a scored-headline count per symbol."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT symbol, COUNT(*) AS n
              FROM headlines
             WHERE sentiment_label IS NOT NULL
             GROUP BY symbol
            """
        ).fetchall()
    counts = {r["symbol"]: int(r["n"]) for r in rows}
    return [
        {
            "symbol": t.symbol,
            "name": t.name,
            "sector": t.sector,
            "headline_count": counts.get(t.symbol, 0),
        }
        for t in UNIVERSE
    ]


def get_timeseries(
    symbol: str, days: Optional[int] = None, relevant_only: bool = True
) -> dict:
    """Return aligned price and daily-sentiment points for one ticker."""
    prices = load_price_series(symbol)
    if prices.empty:
        return {"symbol": symbol, "points": [], "n_sessions": 0}

    sentiment_df = load_daily_sentiment(symbol, relevant_only=relevant_only)
    daily = map_to_trading_days(sentiment_df, prices.index)

    # Headline counts per session, mapped the same way as the scores.
    counts = pd.Series(0, index=prices.index, dtype=int)
    if not sentiment_df.empty:
        idx = pd.DatetimeIndex(sorted(prices.index))
        pos = idx.searchsorted(sentiment_df.index, side="left")
        tmp = sentiment_df.copy()
        tmp["slot"] = pos
        tmp = tmp[tmp["slot"] < len(idx)]
        if not tmp.empty:
            tmp["session"] = idx[tmp["slot"].to_numpy()]
            grouped = tmp.groupby("session")["n_headlines"].sum()
            counts = grouped.reindex(prices.index).fillna(0).astype(int)

    if days is not None and days > 0:
        prices = prices.tail(days)
        daily = daily.reindex(prices.index)
        counts = counts.reindex(prices.index).fillna(0).astype(int)

    points = []
    for date, close in prices.items():
        raw = daily.get(date) if date in daily.index else None
        points.append(
            {
                "date": pd.Timestamp(date).date().isoformat(),
                "close": _safe_float(close),
                "sentiment": None if raw is None or pd.isna(raw) else _safe_float(raw),
                "headline_count": int(counts.get(date, 0)),
            }
        )
    return {"symbol": symbol, "points": points, "n_sessions": len(points)}


def get_headlines(
    symbol: str, limit: int = 20, relevant_only: bool = False
) -> list[dict]:
    """Return the most recent scored headlines for a ticker."""
    clause = " AND is_relevant = 1" if relevant_only else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT headline, source, url, published_at,
                   sentiment_label, sentiment_score, sentiment_confidence,
                   is_relevant
              FROM headlines
             WHERE symbol = ?
               AND sentiment_label IS NOT NULL{clause}
             ORDER BY published_at DESC
             LIMIT ?
            """,
            (symbol, limit),
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "headline": r["headline"],
                "source": r["source"],
                "url": r["url"],
                "published_at": r["published_at"],
                "sentiment_label": r["sentiment_label"],
                "sentiment_score": _safe_float(r["sentiment_score"]),
                "sentiment_confidence": _safe_float(r["sentiment_confidence"]),
                "is_relevant": None
                if r["is_relevant"] is None
                else bool(r["is_relevant"]),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Corpus statistics
# ---------------------------------------------------------------------------
def get_stats() -> dict:
    """Return counts and the sentiment distribution over the whole corpus."""
    n_headlines = count_rows("headlines")
    with get_connection() as conn:
        scored = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM headlines WHERE sentiment_label IS NOT NULL"
            ).fetchone()["n"]
        )
        relevant = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM headlines WHERE is_relevant = 1"
            ).fetchone()["n"]
        )
        dist_rows = conn.execute(
            """
            SELECT sentiment_label AS label,
                   COUNT(*) AS n,
                   AVG(sentiment_score) AS avg_score,
                   AVG(sentiment_confidence) AS avg_conf
              FROM headlines
             WHERE sentiment_label IS NOT NULL
             GROUP BY sentiment_label
             ORDER BY n DESC
            """
        ).fetchall()

    distribution = [
        {
            "label": r["label"],
            "count": int(r["n"]),
            "share": _safe_float(r["n"] / scored) if scored else 0.0,
            "avg_score": _safe_float(r["avg_score"]),
            "avg_confidence": _safe_float(r["avg_conf"]),
        }
        for r in dist_rows
    ]

    return {
        "n_tickers": count_rows("tickers"),
        "n_prices": count_rows("prices"),
        "n_headlines": n_headlines,
        "n_scored": scored,
        "scored_pct": _safe_float(scored / n_headlines * 100) if n_headlines else 0.0,
        "n_relevant": relevant,
        "relevant_pct": _safe_float(relevant / n_headlines * 100)
        if n_headlines
        else 0.0,
        "distribution": distribution,
    }


# ---------------------------------------------------------------------------
# Evaluation (expensive - always served from cache)
# ---------------------------------------------------------------------------
def _ic_payload(result) -> dict:
    return {
        "mean_ic": _safe_float(result.mean_ic),
        "t_stat": _safe_float(result.t_stat),
        "p_value": _safe_float(result.p_value),
        "n_days": int(result.n_days),
        "hit_rate": _safe_float(result.hit_rate),
        "significant": bool(result.p_value < 0.05),
    }


def _perf_payload(label: str, stats: dict) -> dict:
    return {
        "label": label,
        "total_return": _safe_float(stats["total_return"]),
        "annualized_return": _safe_float(stats["annualized_return"]),
        "annualized_volatility": _safe_float(stats["annualized_volatility"]),
        "sharpe_ratio": _safe_float(stats["sharpe_ratio"]),
        "max_drawdown": _safe_float(stats["max_drawdown"]),
        "n_days": int(stats["n_days"]),
    }


def _verdict(ic_oos: dict) -> str:
    """Plain-language reading of the out-of-sample result."""
    if ic_oos["n_days"] < 30:
        return (
            "Too few out-of-sample sessions to draw a conclusion. Widen the "
            "news coverage before interpreting these numbers."
        )
    if ic_oos["significant"]:
        direction = "positive" if ic_oos["mean_ic"] > 0 else "negative"
        return (
            f"The signal shows a statistically significant {direction} "
            f"information coefficient of {ic_oos['mean_ic']:+.4f} "
            f"(p={ic_oos['p_value']:.3f}) out of sample."
        )
    return (
        f"No predictive signal detected. The out-of-sample information "
        f"coefficient is {ic_oos['mean_ic']:+.4f} (p={ic_oos['p_value']:.3f}), "
        "statistically indistinguishable from zero. This is the expected result "
        "for daily-horizon news sentiment on heavily-traded large-cap equities."
    )


def compute_evaluation(
    train_frac: float = 0.6, cost_bps: float = 5.0, relevant_only: bool = True
) -> dict:
    """Run the full evaluation. Expensive; callers should cache the result."""
    signals, forwards = build_panel(window=3, relevant_only=relevant_only)
    if signals.empty:
        raise ValueError("No panel data available. Run the ingest and scoring first.")

    coverage = coverage_report(signals)
    signals, forwards = trim_to_coverage(signals, forwards)
    ic_full = information_coefficient(signals, forwards)

    (tr_s, tr_f), (te_s, te_f) = split_panel(signals, forwards, train_frac=train_frac)

    # Select parameters on the training window only.
    best = None
    for window in WINDOW_GRID:
        s_all, f_all = build_panel(window=window, relevant_only=relevant_only)
        s_all, f_all = trim_to_coverage(s_all, f_all)
        (s_tr, f_tr), _ = split_panel(s_all, f_all, train_frac=train_frac)
        for top_n in TOP_N_GRID:
            res = cross_sectional_backtest(s_tr, f_tr, top_n=top_n, cost_bps=cost_bps)
            stats = summarize_returns(res["returns"])
            if best is None or stats["sharpe_ratio"] > best[2]:
                best = (window, top_n, stats["sharpe_ratio"])

    window, top_n, _ = best

    s_all, f_all = build_panel(window=window, relevant_only=relevant_only)
    s_all, f_all = trim_to_coverage(s_all, f_all)
    (s_tr, f_tr), (s_te, f_te) = split_panel(s_all, f_all, train_frac=train_frac)

    ins = summarize_returns(
        cross_sectional_backtest(s_tr, f_tr, top_n=top_n, cost_bps=cost_bps)["returns"]
    )
    oos = summarize_returns(
        cross_sectional_backtest(s_te, f_te, top_n=top_n, cost_bps=cost_bps)["returns"]
    )
    bh = summarize_returns(f_te.mean(axis=1).dropna())
    ic_oos = _ic_payload(information_coefficient(s_te, f_te))

    return {
        "coverage": {
            "total_sessions": coverage["total_sessions"],
            "covered_sessions": coverage["covered_sessions"],
            "coverage_pct": _safe_float(coverage["coverage_pct"]),
            "first_covered": coverage["first_covered"].date().isoformat()
            if coverage["first_covered"] is not None
            else None,
            "last_covered": coverage["last_covered"].date().isoformat()
            if coverage["last_covered"] is not None
            else None,
        },
        "ic_full_sample": _ic_payload(ic_full),
        "ic_out_of_sample": ic_oos,
        "performance": [
            _perf_payload("Long/short (in-sample)", ins),
            _perf_payload("Long/short (out-of-sample)", oos),
            _perf_payload("Buy & hold (same window)", bh),
        ],
        "selected_window": window,
        "selected_top_n": top_n,
        "train_sessions": len(s_tr),
        "test_sessions": len(s_te),
        "verdict": _verdict(ic_oos),
    }