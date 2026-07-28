"""Rigorous evaluation of the sentiment signal.

This is the script that makes the project defensible rather than merely
impressive-looking. It reports, in order:

1. **Information coefficient** -- does the signal carry any predictive
   information at all, before any trading logic is layered on?
2. **Relevance-filter comparison** -- does dropping headlines that never
   mention the company improve that number?
3. **In-sample parameter selection** -- parameters are chosen using only the
   first `--train-frac` of the timeline.
4. **Out-of-sample results** -- the chosen parameters are then run once on
   the held-out remainder, and that number is the one reported.

Point 4 is the whole discipline. Tuning parameters until a backtest looks
good is trivial and meaningless; the honest question is whether the choice
made on past data survives on data it never saw.

Usage
-----
    python -m scripts.run_evaluation
    python -m scripts.run_evaluation --relevant-only
    python -m scripts.run_evaluation --train-frac 0.7 --cost-bps 10
"""
from __future__ import annotations

import argparse

import pandas as pd

from src.evaluation import (
    cross_sectional_backtest,
    information_coefficient,
    summarize_returns,
)
from src.panel import build_panel, coverage_report, split_panel, trim_to_coverage

WINDOW_GRID = [1, 2, 3, 5, 10]
TOP_N_GRID = [3, 5, 7]


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def _print_ic(label: str, res) -> None:
    stars = ""
    if res.p_value < 0.01:
        stars = " ***"
    elif res.p_value < 0.05:
        stars = " **"
    elif res.p_value < 0.10:
        stars = " *"
    print(
        f"  {label:<28} IC {res.mean_ic:+.4f}  "
        f"t={res.t_stat:+.2f}  p={res.p_value:.3f}{stars}  "
        f"({res.n_days} days, {res.hit_rate:.0%} positive)"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate the sentiment signal")
    ap.add_argument("--train-frac", type=float, default=0.6)
    ap.add_argument("--cost-bps", type=float, default=5.0)
    ap.add_argument(
        "--relevant-only",
        action="store_true",
        help="Use only headlines that mention the company.",
    )
    args = ap.parse_args()

    print("=" * 74)
    print("SENTIMENT SIGNAL EVALUATION")
    print("=" * 74)

    # ---------------------------------------------------------------- IC ---
    print("\n[1] INFORMATION COEFFICIENT  (signal vs next-day return, rank corr.)")
    print("    Real equity signals typically live in the 0.02-0.05 range.\n")

    for flag, label in ((False, "all headlines"), (True, "relevance-filtered")):
        sig, fwd = build_panel(window=3, relevant_only=flag)
        if sig.empty:
            print(f"  {label:<28} no data")
            continue
        _print_ic(label, information_coefficient(sig, fwd))

    # ------------------------------------------------------------- panel ---
    signals, forwards = build_panel(window=3, relevant_only=args.relevant_only)
    if signals.empty:
        print("\nNo panel data. Run the ingest and scoring scripts first.")
        return

    # ---------------------------------------------------------- coverage ---
    cov = coverage_report(signals)
    print("\n[1b] NEWS COVERAGE")
    print(
        f"    {cov['covered_sessions']} of {cov['total_sessions']} price sessions "
        f"have news for 3+ tickers ({cov['coverage_pct']:.1f}%)."
    )
    if cov["first_covered"] is not None:
        print(
            f"    Covered span: {cov['first_covered'].date()} -> "
            f"{cov['last_covered'].date()}"
        )
    if cov["coverage_pct"] < 50:
        print(
            "\n    ** Most of the price history has no news behind it. Sessions\n"
            "       without news are dropped below, so the effective sample is the\n"
            "       covered span only. Widen coverage by re-running the ingest with\n"
            "       the paginated news fetcher. **"
        )

    # Restrict everything downstream to sessions that actually have news.
    signals, forwards = trim_to_coverage(signals, forwards)
    if len(signals) < 20:
        print(
            f"\n    Only {len(signals)} usable sessions. That is too few for a\n"
            "    train/test split to mean anything. Re-run the ingest first."
        )
        return

    (tr_s, tr_f), (te_s, te_f) = split_panel(
        signals, forwards, train_frac=args.train_frac
    )
    print(
        f"\n[2] TRAIN / TEST SPLIT   train={len(tr_s)} sessions "
        f"({tr_s.index.min().date()} -> {tr_s.index.max().date()}), "
        f"test={len(te_s)} sessions "
        f"({te_s.index.min().date()} -> {te_s.index.max().date()})"
    )

    # --------------------------------------------- in-sample selection ---
    print(f"\n[3] IN-SAMPLE PARAMETER SEARCH  ({len(WINDOW_GRID) * len(TOP_N_GRID)} "
          "combinations, train data only)\n")
    print(f"    {'window':>7}{'top_n':>7}{'Sharpe':>10}{'Return':>10}")
    print("    " + "-" * 34)

    best = None
    for window in WINDOW_GRID:
        # Rebuild the panel per window, then re-split identically.
        s_all, f_all = build_panel(window=window, relevant_only=args.relevant_only)
        s_all, f_all = trim_to_coverage(s_all, f_all)
        (s_tr, f_tr), _ = split_panel(s_all, f_all, train_frac=args.train_frac)
        for top_n in TOP_N_GRID:
            res = cross_sectional_backtest(
                s_tr, f_tr, top_n=top_n, cost_bps=args.cost_bps
            )
            stats = summarize_returns(res["returns"])
            print(
                f"    {window:>7}{top_n:>7}{stats['sharpe_ratio']:>10.2f}"
                f"{_pct(stats['total_return']):>10}"
            )
            if best is None or stats["sharpe_ratio"] > best[2]:
                best = (window, top_n, stats["sharpe_ratio"])

    window, top_n, train_sharpe = best
    print(
        f"\n    Selected: window={window}, top_n={top_n} "
        f"(train Sharpe {train_sharpe:.2f})"
    )

    # ------------------------------------------------ out-of-sample ---
    s_all, f_all = build_panel(window=window, relevant_only=args.relevant_only)
    s_all, f_all = trim_to_coverage(s_all, f_all)
    (s_tr, f_tr), (s_te, f_te) = split_panel(
        s_all, f_all, train_frac=args.train_frac
    )

    oos = cross_sectional_backtest(s_te, f_te, top_n=top_n, cost_bps=args.cost_bps)
    oos_stats = summarize_returns(oos["returns"])
    ins = cross_sectional_backtest(s_tr, f_tr, top_n=top_n, cost_bps=args.cost_bps)
    ins_stats = summarize_returns(ins["returns"])

    # Equal-weight buy-and-hold over the same out-of-sample window.
    bh_oos = summarize_returns(f_te.mean(axis=1).dropna())

    print("\n[4] OUT-OF-SAMPLE RESULT  (parameters never saw this data)\n")
    header = f"    {'':<22}{'Return':>10}{'Sharpe':>9}{'Vol':>9}{'MaxDD':>10}{'Days':>7}"
    print(header)
    print("    " + "-" * 67)
    for name, st in (
        ("Long/short IN-SAMPLE", ins_stats),
        ("Long/short OUT-OF-SAMPLE", oos_stats),
        ("Buy & hold (same window)", bh_oos),
    ):
        print(
            f"    {name:<22}{_pct(st['total_return']):>10}"
            f"{st['sharpe_ratio']:>9.2f}{_pct(st['annualized_volatility']):>9}"
            f"{_pct(st['max_drawdown']):>10}{st['n_days']:>7}"
        )

    print("\n[5] OUT-OF-SAMPLE INFORMATION COEFFICIENT\n")
    _print_ic("held-out test window", information_coefficient(s_te, f_te))

    # -------------------------------------------------------- caveats ---
    print("\n" + "=" * 74)
    print("READING THESE NUMBERS")
    print("=" * 74)
    decay = ins_stats["sharpe_ratio"] - oos_stats["sharpe_ratio"]
    print(
        f"  In-sample Sharpe {ins_stats['sharpe_ratio']:.2f} -> out-of-sample "
        f"{oos_stats['sharpe_ratio']:.2f} (decay {decay:+.2f})."
    )
    print(
        "  Large decay is normal and expected: it is the cost of having chosen\n"
        "  parameters on the training window. The out-of-sample figure is the\n"
        "  only one worth quoting."
    )
    if oos_stats["n_days"] < 60:
        print(
            f"\n  ** Only {oos_stats['n_days']} out-of-sample sessions. Too few to\n"
            "     support a strong claim either way. **"
        )
    print(
        "\n  The long/short book is dollar-neutral, so it is not directly\n"
        "  comparable to buy-and-hold: it targets a different risk exposure\n"
        "  (relative performance within the universe, not market direction)."
    )


if __name__ == "__main__":
    main()