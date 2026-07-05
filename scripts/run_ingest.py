"""End-to-end Phase 1 ingest: build the DB, load tickers, pull prices & news.

Usage
-----
    python -m scripts.run_ingest                # full run (prices + news)
    python -m scripts.run_ingest --prices-only  # skip news (no API key needed)
    python -m scripts.run_ingest --limit 5      # only the first 5 tickers

Run from the project root so the imports resolve.
"""
from __future__ import annotations

import argparse
import logging

from src.database import init_db, upsert_tickers, count_rows
from src.ingest_news import ingest_news
from src.ingest_prices import ingest_prices
from src.tickers import UNIVERSE, symbols

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_ingest")


def main() -> None:
    parser = argparse.ArgumentParser(description="FinSent Phase 1 data ingest")
    parser.add_argument(
        "--prices-only",
        action="store_true",
        help="Skip news ingestion (useful before you have a Finnhub key).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only ingest the first N tickers (handy for quick tests).",
    )
    args = parser.parse_args()

    logger.info("Initializing database schema...")
    init_db()

    logger.info("Loading %d tickers into the universe...", len(UNIVERSE))
    upsert_tickers((t.symbol, t.name, t.sector) for t in UNIVERSE)

    syms = symbols()
    if args.limit:
        syms = syms[: args.limit]
    logger.info("Ingesting data for %d tickers: %s", len(syms), ", ".join(syms))

    logger.info("=== Prices ===")
    price_rows = ingest_prices(syms)
    logger.info("Inserted %d new price rows.", price_rows)

    if not args.prices_only:
        logger.info("=== News ===")
        news_rows = ingest_news(syms)
        logger.info("Inserted %d new headlines.", news_rows)

    logger.info(
        "Done. DB totals -> tickers: %d | prices: %d | headlines: %d",
        count_rows("tickers"),
        count_rows("prices"),
        count_rows("headlines"),
    )


if __name__ == "__main__":
    main()
