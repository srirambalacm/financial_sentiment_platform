"""Build a compact, serving-only copy of the database for deployment.

The working database carries columns that only ingestion needs. `dedup_hash`
exists so a re-ingest can skip headlines it already has, and `fetched_at`
records when a row arrived — neither is ever read by the API. On a 120K-row
corpus those columns and their index are a meaningful share of the file, and a
deployed read-only API pays for them on every clone and cold start.

This script produces `data/finsent-deploy.db` with:

  * `dedup_hash` and `fetched_at` dropped from `headlines`
  * the ingestion-only unique index removed
  * VACUUM run to reclaim the freed pages

Row counts are preserved exactly, so every figure the API reports — headline
totals, relevance retention, the sentiment distribution — stays identical to
the numbers quoted in the README. Shrinking the file must not quietly change
the findings.

Usage
-----
    python -m scripts.build_deploy_db
    python -m scripts.build_deploy_db --output data/serve.db
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

from config import DB_PATH

SERVING_SCHEMA = """
CREATE TABLE headlines_new (
    id                   INTEGER PRIMARY KEY,
    symbol               TEXT NOT NULL REFERENCES tickers(symbol),
    headline             TEXT NOT NULL,
    source               TEXT,
    url                  TEXT,
    published_at         TEXT NOT NULL,
    sentiment_label      TEXT,
    sentiment_score      REAL,
    sentiment_confidence REAL,
    is_relevant          INTEGER
);

INSERT INTO headlines_new
    (id, symbol, headline, source, url, published_at,
     sentiment_label, sentiment_score, sentiment_confidence, is_relevant)
SELECT id, symbol, headline, source, url, published_at,
       sentiment_label, sentiment_score, sentiment_confidence, is_relevant
  FROM headlines;

DROP TABLE headlines;
ALTER TABLE headlines_new RENAME TO headlines;

CREATE INDEX IF NOT EXISTS idx_headlines_symbol_pub
    ON headlines (symbol, published_at);
CREATE INDEX IF NOT EXISTS idx_headlines_scored
    ON headlines (sentiment_label);
"""


def _mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def _counts(conn: sqlite3.Connection) -> dict:
    """Row counts and the figures the API reports, for before/after comparison."""
    q = lambda sql: int(conn.execute(sql).fetchone()[0])  # noqa: E731
    return {
        "tickers": q("SELECT COUNT(*) FROM tickers"),
        "prices": q("SELECT COUNT(*) FROM prices"),
        "headlines": q("SELECT COUNT(*) FROM headlines"),
        "scored": q("SELECT COUNT(*) FROM headlines WHERE sentiment_label IS NOT NULL"),
        "relevant": q("SELECT COUNT(*) FROM headlines WHERE is_relevant = 1"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a deployment database")
    ap.add_argument(
        "--source", default=str(DB_PATH), help="Working database to copy from."
    )
    ap.add_argument(
        "--output",
        default="data/finsent-deploy.db",
        help="Where to write the compacted database.",
    )
    args = ap.parse_args()

    source = Path(args.source)
    output = Path(args.output)

    if not source.exists():
        print(f"Source database not found: {source}")
        print("Run the ingest and scoring scripts first.")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    print("=" * 64)
    print("Building deployment database")
    print("=" * 64)
    print(f"  source: {source}  ({_mb(source):.1f} MB)")

    with sqlite3.connect(source) as conn:
        before = _counts(conn)

    shutil.copy2(source, output)

    with sqlite3.connect(output) as conn:
        conn.executescript(SERVING_SCHEMA)
        conn.commit()
    # VACUUM cannot run inside a transaction, so it gets its own connection.
    with sqlite3.connect(output) as conn:
        conn.execute("VACUUM")

    with sqlite3.connect(output) as conn:
        after = _counts(conn)

    print(f"  output: {output}  ({_mb(output):.1f} MB)")
    saved = _mb(source) - _mb(output)
    pct = (saved / _mb(source) * 100) if _mb(source) else 0
    print(f"  saved:  {saved:.1f} MB  ({pct:.0f}% smaller)")

    print("\n  Row counts (must be unchanged):")
    ok = True
    for key in before:
        match = "OK" if before[key] == after[key] else "MISMATCH"
        if before[key] != after[key]:
            ok = False
        print(f"    {key:<11} {before[key]:>8,} -> {after[key]:>8,}   {match}")

    print("\n" + "=" * 64)
    if ok:
        print("  Deployment database ready. Commit it (it is not gitignored by")
        print("  default — add an exception) or upload it to your host.")
    else:
        print("  ROW COUNTS CHANGED — do not deploy this file.")
    print("=" * 64)


if __name__ == "__main__":
    main()