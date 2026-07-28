"""Print a health summary of the FinSent database.

Useful as a sanity check between phases: confirms row counts, how much of the
corpus has been scored, the sentiment distribution, and a few sample rows.

Usage
-----
    python -m scripts.inspect_db
"""
from __future__ import annotations

from src.database import get_connection, count_rows, init_db


def main() -> None:
    # Ensure the schema exists so this never crashes on a fresh database.
    init_db()

    print("=" * 62)
    print("FinSent database summary")
    print("=" * 62)

    for table in ("tickers", "prices", "headlines"):
        print(f"  {table:<10} rows: {count_rows(table):,}")

    with get_connection() as conn:
        scored = conn.execute(
            "SELECT COUNT(*) AS n FROM headlines WHERE sentiment_label IS NOT NULL"
        ).fetchone()["n"]
        total = conn.execute("SELECT COUNT(*) AS n FROM headlines").fetchone()["n"]
        pct = (scored / total * 100) if total else 0.0
        print(f"\n  Scored headlines: {scored:,} / {total:,}  ({pct:.1f}%)")

        if scored:
            print("\n  Sentiment distribution:")
            rows = conn.execute(
                """
                SELECT sentiment_label AS label,
                       COUNT(*)        AS n,
                       AVG(sentiment_score)      AS avg_score,
                       AVG(sentiment_confidence) AS avg_conf
                  FROM headlines
                 WHERE sentiment_label IS NOT NULL
                 GROUP BY sentiment_label
                 ORDER BY n DESC
                """
            ).fetchall()
            for r in rows:
                share = r["n"] / scored * 100
                print(
                    f"    {r['label']:<9} {r['n']:>6,}  ({share:>5.1f}%)   "
                    f"avg score {r['avg_score']:+.3f}   avg conf {r['avg_conf']:.3f}"
                )

            print("\n  Sample scored headlines:")
            samples = conn.execute(
                """
                SELECT symbol, sentiment_label, sentiment_score, headline
                  FROM headlines
                 WHERE sentiment_label IS NOT NULL
                 ORDER BY RANDOM()
                 LIMIT 5
                """
            ).fetchall()
            for r in samples:
                text = r["headline"][:64] + ("..." if len(r["headline"]) > 64 else "")
                print(
                    f"    [{r['symbol']:<5}] {r['sentiment_label']:<8} "
                    f"{r['sentiment_score']:+.2f}  {text}"
                )
        else:
            print("\n  No headlines scored yet — run: python -m scripts.score_headlines")

    print("=" * 62)


if __name__ == "__main__":
    main()