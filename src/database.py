"""SQLite data-access layer for FinSent.

This module owns the schema and every read/write against the database. Keeping
all SQL in one place (a lightweight repository pattern) means the ingestion
scripts, the future API, and the tests all share one consistent interface.

Schema overview
---------------
tickers    : the stock universe we track (symbol is the primary key)
prices     : daily OHLCV bars, one row per (symbol, date)
headlines  : news headlines, deduplicated, with nullable sentiment columns
             that Phase 2 (the FinBERT scorer) will populate.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator, Optional

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickers (
    symbol     TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    sector     TEXT NOT NULL,
    added_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prices (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT NOT NULL REFERENCES tickers(symbol),
    date      TEXT NOT NULL,            -- ISO date, e.g. 2027-01-15
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    adj_close REAL,
    volume    INTEGER,
    UNIQUE (symbol, date)
);

CREATE TABLE IF NOT EXISTS headlines (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol               TEXT NOT NULL REFERENCES tickers(symbol),
    headline             TEXT NOT NULL,
    source               TEXT,
    url                  TEXT,
    published_at         TEXT NOT NULL,   -- ISO datetime
    fetched_at           TEXT NOT NULL DEFAULT (datetime('now')),
    dedup_hash           TEXT NOT NULL,   -- sha1(symbol|headline|published_at)
    -- Populated later by the Phase 2 sentiment pipeline:
    sentiment_label      TEXT,            -- positive | negative | neutral
    sentiment_score      REAL,            -- signed score in [-1, 1]
    sentiment_confidence REAL,            -- model confidence in [0, 1]
    UNIQUE (dedup_hash)
);

CREATE INDEX IF NOT EXISTS idx_prices_symbol_date
    ON prices (symbol, date);
CREATE INDEX IF NOT EXISTS idx_headlines_symbol_pub
    ON headlines (symbol, published_at);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------
@contextmanager
def get_connection(db_path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with foreign keys on and Row access.

    Commits on success, rolls back on error, and always closes the handle.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str = DB_PATH) -> None:
    """Create all tables and indexes if they do not already exist."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive schema changes to databases created by older versions.

    SQLite has no 'ADD COLUMN IF NOT EXISTS', so we inspect the table first.
    This keeps existing data intact instead of forcing a rebuild.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(headlines)")}
    if "is_relevant" not in existing:
        # NULL = not yet evaluated, 1 = mentions the company, 0 = does not.
        conn.execute("ALTER TABLE headlines ADD COLUMN is_relevant INTEGER")


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def upsert_tickers(rows: Iterable[tuple[str, str, str]], db_path: Path | str = DB_PATH) -> int:
    """Insert or update ticker rows. Each row is (symbol, name, sector).

    Returns the number of rows written.
    """
    rows = list(rows)
    with get_connection(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO tickers (symbol, name, sector)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name,
                sector = excluded.sector
            """,
            rows,
        )
    return len(rows)


def upsert_prices(rows: Iterable[dict], db_path: Path | str = DB_PATH) -> int:
    """Insert daily price bars, ignoring duplicates on (symbol, date).

    Each row is a dict with keys: symbol, date, open, high, low, close,
    adj_close, volume. Returns the number of newly inserted rows.
    """
    rows = list(rows)
    if not rows:
        return 0
    with get_connection(db_path) as conn:
        before = conn.total_changes
        conn.executemany(
            """
            INSERT OR IGNORE INTO prices
                (symbol, date, open, high, low, close, adj_close, volume)
            VALUES
                (:symbol, :date, :open, :high, :low, :close, :adj_close, :volume)
            """,
            rows,
        )
        return conn.total_changes - before


def _dedup_hash(symbol: str, headline: str, published_at: str) -> str:
    key = f"{symbol}|{headline}|{published_at}".encode("utf-8")
    return hashlib.sha1(key).hexdigest()


def upsert_headlines(rows: Iterable[dict], db_path: Path | str = DB_PATH) -> int:
    """Insert news headlines, deduplicating on a content hash.

    Each row is a dict with keys: symbol, headline, source, url, published_at.
    Returns the number of newly inserted (non-duplicate) rows.
    """
    prepared = []
    for r in rows:
        prepared.append(
            {
                **r,
                "dedup_hash": _dedup_hash(
                    r["symbol"], r["headline"], r["published_at"]
                ),
            }
        )
    if not prepared:
        return 0
    with get_connection(db_path) as conn:
        before = conn.total_changes
        conn.executemany(
            """
            INSERT OR IGNORE INTO headlines
                (symbol, headline, source, url, published_at, dedup_hash)
            VALUES
                (:symbol, :headline, :source, :url, :published_at, :dedup_hash)
            """,
            prepared,
        )
        return conn.total_changes - before


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def count_rows(table: str, db_path: Path | str = DB_PATH) -> int:
    """Return the number of rows in a table. Table name is validated."""
    if table not in {"tickers", "prices", "headlines"}:
        raise ValueError(f"Unknown table: {table}")
    with get_connection(db_path) as conn:
        cur = conn.execute(f"SELECT COUNT(*) AS n FROM {table}")
        return int(cur.fetchone()["n"])


def get_prices(symbol: str, db_path: Path | str = DB_PATH) -> list[sqlite3.Row]:
    """Return all price bars for a symbol, oldest first."""
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM prices WHERE symbol = ? ORDER BY date ASC", (symbol,)
        )
        return cur.fetchall()


def get_headlines(
    symbol: str, limit: Optional[int] = None, db_path: Path | str = DB_PATH
) -> list[sqlite3.Row]:
    """Return headlines for a symbol, newest first, optionally limited."""
    sql = "SELECT * FROM headlines WHERE symbol = ? ORDER BY published_at DESC"
    params: tuple = (symbol,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (symbol, limit)
    with get_connection(db_path) as conn:
        return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------------
# Sentiment (Phase 2)
# ---------------------------------------------------------------------------
def get_unscored_headlines(
    limit: Optional[int] = None,
    db_path: Path | str = DB_PATH,
    relevant_only: bool = False,
) -> list[sqlite3.Row]:
    """Return headlines that have not yet been scored (sentiment is NULL).

    Ordered by id so scoring runs are deterministic and resumable: if a run
    is interrupted, the next run simply picks up the still-unscored rows.

    With `relevant_only`, restricts to headlines that passed the relevance
    filter — useful for skipping model inference on text that would be
    filtered out of the signal anyway.
    """
    clause = " AND is_relevant = 1" if relevant_only else ""
    sql = (
        "SELECT id, headline FROM headlines "
        f"WHERE sentiment_label IS NULL{clause} ORDER BY id"
    )
    params: tuple = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    with get_connection(db_path) as conn:
        return conn.execute(sql, params).fetchall()


def get_headlines_for_relevance(
    db_path: Path | str = DB_PATH,
) -> list[sqlite3.Row]:
    """Return (id, symbol, headline) for every headline, for relevance tagging."""
    with get_connection(db_path) as conn:
        return conn.execute(
            "SELECT id, symbol, headline FROM headlines ORDER BY id"
        ).fetchall()


def update_relevance(
    updates: Iterable[tuple[int, int]], db_path: Path | str = DB_PATH
) -> int:
    """Write relevance flags. Each update is (is_relevant, headline_id)."""
    updates = list(updates)
    if not updates:
        return 0
    with get_connection(db_path) as conn:
        before = conn.total_changes
        conn.executemany(
            "UPDATE headlines SET is_relevant = ? WHERE id = ?", updates
        )
        return conn.total_changes - before


def get_sentiment_by_date(
    symbol: str,
    db_path: Path | str = DB_PATH,
    relevant_only: bool = False,
) -> list[sqlite3.Row]:
    """Return per-day aggregated sentiment for one symbol.

    Groups scored headlines by their UTC publication date and returns
    (date, avg_score, n_headlines) ordered oldest first. The count is
    returned so callers can compute a properly weighted mean when several
    news dates are combined into a single trading day.

    With `relevant_only`, headlines that failed the relevance filter are
    excluded (rows never tagged are treated as not relevant).
    """
    clause = " AND is_relevant = 1" if relevant_only else ""
    with get_connection(db_path) as conn:
        return conn.execute(
            f"""
            SELECT substr(published_at, 1, 10) AS date,
                   AVG(sentiment_score)        AS avg_score,
                   COUNT(*)                    AS n_headlines
              FROM headlines
             WHERE symbol = ?
               AND sentiment_label IS NOT NULL{clause}
             GROUP BY date
             ORDER BY date ASC
            """,
            (symbol,),
        ).fetchall()


def update_sentiment(
    updates: Iterable[tuple[str, float, float, int]], db_path: Path | str = DB_PATH
) -> int:
    """Write sentiment results back to headlines.

    Each update is a tuple of (label, score, confidence, headline_id).
    Returns the number of rows updated.
    """
    updates = list(updates)
    if not updates:
        return 0
    with get_connection(db_path) as conn:
        before = conn.total_changes
        conn.executemany(
            """
            UPDATE headlines
               SET sentiment_label = ?,
                   sentiment_score = ?,
                   sentiment_confidence = ?
             WHERE id = ?
            """,
            updates,
        )
        return conn.total_changes - before