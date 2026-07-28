"""Backtest the sentiment signal across the ticker universe.

Runs the strategy per ticker, then aggregates into an equal-weight portfolio
and compares it to an equal-weight buy-and-hold baseline over the identical
window.

Usage
-----
    python -m scripts.run_backtest
    python -m scripts.run_backtest --window 5 --threshold 0.15
    python -m scripts.run_backtest --allow-short --cost-bps 10
    python -m scripts.run_backtest --csv results.csv
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from src.backtest import performance_metrics, run_backtest
from src.signals import build_positions
from src.tickers import symbols

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)-7s  %(message)s",
)
logger = logging.getLogger("run_backtest")

# Below this many sessions, results are noise rather than evidence.
MIN_MEANINGFUL_SESSIONS = 60


def _pct(x: float) -> str:
    return f"{x * 100:>7.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the sentiment signal")
    parser.add_argument("--window", type=int, default=3, help="Rolling window (days).")
    parser.add_argument(
        "--threshold", type=float, default=0.1, help="Signal threshold to go long."
    )
    parser.add_argument(
        "--allow-short", action="store_true", help="Also short on negative sentiment."
    )
    parser.add_argument(
        "--cost-bps", type=float, default=5.0, help="Per-trade cost in basis points."
    )
    parser.add_argument("--csv", type=str, default=None, help="Write per-ticker CSV.")
    args = parser.parse_args()

    print("=" * 86)
    print(
        f"Sentiment backtest  |  window={args.window}d  threshold={args.threshold}  "
        f"short={args.allow_short}  cost={args.cost_bps}bps"
    )
    print("=" * 86)
    header = (
        f"{'Ticker':<8}{'Strat Ret':>11}{'B&H Ret':>11}{'Excess':>10}"
        f"{'Sharpe':>9}{'MaxDD':>10}{'Expo':>8}{'Trades':>8}{'Days':>7}"
    )
    print(header)
    print("-" * 86)

    strat_streams: dict[str, pd.Series] = {}
    bench_streams: dict[str, pd.Series] = {}
    rows: list[dict] = []

    for symbol in symbols():
        prices, positions = build_positions(
            symbol,
            window=args.window,
            threshold=args.threshold,
            allow_short=args.allow_short,
        )
        if prices.empty or positions.empty:
            logger.warning("%s: no data, skipped.", symbol)
            continue

        result = run_backtest(prices, positions, cost_bps=args.cost_bps)
        s, b = result["strategy"], result["benchmark"]

        # Only score the window where a signal could actually exist.
        active = result["strategy_returns"]
        if active.empty:
            continue

        strat_streams[symbol] = result["strategy_returns"]
        bench_streams[symbol] = result["benchmark_returns"]

        excess = s.total_return - b.total_return
        print(
            f"{symbol:<8}{_pct(s.total_return):>11}{_pct(b.total_return):>11}"
            f"{_pct(excess):>10}{s.sharpe_ratio:>9.2f}{_pct(s.max_drawdown):>10}"
            f"{result['exposure'] * 100:>7.0f}%{result['n_trades']:>8}{s.n_days:>7}"
        )
        rows.append(
            {
                "symbol": symbol,
                "strategy_return": s.total_return,
                "benchmark_return": b.total_return,
                "excess_return": excess,
                "strategy_sharpe": s.sharpe_ratio,
                "benchmark_sharpe": b.sharpe_ratio,
                "strategy_max_drawdown": s.max_drawdown,
                "benchmark_max_drawdown": b.max_drawdown,
                "exposure": result["exposure"],
                "n_trades": result["n_trades"],
                "n_days": s.n_days,
            }
        )

    if not rows:
        print("\nNo results. Have you run score_headlines yet?")
        return

    # ---- Equal-weight portfolio -------------------------------------------
    strat_df = pd.DataFrame(strat_streams)
    bench_df = pd.DataFrame(bench_streams)
    port_strat = strat_df.mean(axis=1).dropna()
    port_bench = bench_df.mean(axis=1).dropna()

    ps = performance_metrics(port_strat)
    pb = performance_metrics(port_bench)

    print("-" * 86)
    print(
        f"{'PORTFOLIO':<8}{_pct(ps.total_return):>11}{_pct(pb.total_return):>11}"
        f"{_pct(ps.total_return - pb.total_return):>10}{ps.sharpe_ratio:>9.2f}"
        f"{_pct(ps.max_drawdown):>10}{'':>8}{'':>8}{ps.n_days:>7}"
    )
    print("=" * 86)

    print("\nPortfolio summary (equal weight across %d tickers)" % len(rows))
    print(f"  Strategy   : {_pct(ps.total_return)} total | Sharpe {ps.sharpe_ratio:.2f} "
          f"| MaxDD {_pct(ps.max_drawdown)} | Vol {_pct(ps.annualized_volatility)}")
    print(f"  Buy & hold : {_pct(pb.total_return)} total | Sharpe {pb.sharpe_ratio:.2f} "
          f"| MaxDD {_pct(pb.max_drawdown)} | Vol {_pct(pb.annualized_volatility)}")
    beat = sum(1 for r in rows if r["excess_return"] > 0)
    print(f"  Beat buy-and-hold on {beat}/{len(rows)} tickers.")

    if ps.n_days < MIN_MEANINGFUL_SESSIONS:
        print(
            f"\n  ** CAUTION: only {ps.n_days} trading sessions in the test window. **\n"
            "  That is far too short to draw statistical conclusions. Widen the news\n"
            "  history (FINSENT_NEWS_LOOKBACK_DAYS) and re-run the ingest to extend it."
        )

    if args.csv:
        pd.DataFrame(rows).to_csv(args.csv, index=False)
        print(f"\n  Per-ticker results written to {args.csv}")


if __name__ == "__main__":
    main()