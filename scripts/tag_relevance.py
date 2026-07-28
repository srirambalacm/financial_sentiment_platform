"""Tag every headline as relevant / not relevant to the ticker it arrived under.

Finnhub tags stories loosely, so a meaningful share of the corpus never
mentions the company at all. This writes a boolean flag per headline that the
signal pipeline can filter on.

Usage
-----
    python -m scripts.tag_relevance
"""
from __future__ import annotations

import logging

from src.database import (
    get_headlines_for_relevance,
    init_db,
    update_relevance,
)
from src.relevance import is_relevant
from src.tickers import symbols

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("tag_relevance")


def main() -> None:
    init_db()  # applies the is_relevant column migration if needed
    rows = get_headlines_for_relevance()
    if not rows:
        print("No headlines found. Run the ingest first.")
        return

    updates = []
    per_symbol: dict[str, list[int]] = {s: [] for s in symbols()}
    for r in rows:
        flag = int(is_relevant(r["symbol"], r["headline"]))
        updates.append((flag, r["id"]))
        per_symbol.setdefault(r["symbol"], []).append(flag)

    written = update_relevance(updates)
    kept = sum(f for f, _ in updates)
    total = len(updates)

    print("=" * 62)
    print("Relevance tagging")
    print("=" * 62)
    print(f"  Tagged {written:,} headlines.")
    print(f"  Relevant: {kept:,} / {total:,}  ({kept / total * 100:.1f}%)")
    print("\n  Per-ticker retention:")
    for sym in sorted(per_symbol):
        flags = per_symbol[sym]
        if not flags:
            continue
        pct = sum(flags) / len(flags) * 100
        bar = "#" * int(pct / 5)
        print(f"    {sym:<6} {sum(flags):>5,}/{len(flags):<5,} {pct:>5.1f}%  {bar}")
    print("=" * 62)
    print("\nHeadlines that mention the company are kept; the rest are excluded")
    print("from the signal when running with --relevant-only.")


if __name__ == "__main__":
    main()