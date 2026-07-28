"""Score every unscored headline in the database with FinBERT.

Usage
-----
    python -m scripts.score_headlines              # score all unscored rows
    python -m scripts.score_headlines --limit 100  # score just the first 100

The run is resumable: it only touches rows whose sentiment is still NULL, so
if it is interrupted you can simply run it again to finish the rest.
"""
from __future__ import annotations

import argparse
import logging

from src.database import get_unscored_headlines, update_sentiment, count_rows
from src.sentiment import get_scorer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("score_headlines")

# How many headlines to pull from the DB and score per loop iteration.
CHUNK = 256


def main() -> None:
    parser = argparse.ArgumentParser(description="Score headlines with FinBERT")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to score.")
    args = parser.parse_args()

    scorer = get_scorer()
    total_scored = 0
    remaining = args.limit

    while True:
        take = CHUNK if remaining is None else min(CHUNK, remaining)
        if take <= 0:
            break
        rows = get_unscored_headlines(limit=take)
        if not rows:
            break

        texts = [r["headline"] for r in rows]
        results = scorer.score_batch(texts)

        updates = [
            (res["label"], res["score"], res["confidence"], row["id"])
            for row, res in zip(rows, results)
        ]
        written = update_sentiment(updates)
        total_scored += written
        if remaining is not None:
            remaining -= written
        logger.info("Scored %d headlines so far...", total_scored)

    logger.info("Done. Scored %d headlines this run.", total_scored)
    logger.info("Total headlines in DB: %d", count_rows("headlines"))


if __name__ == "__main__":
    main()