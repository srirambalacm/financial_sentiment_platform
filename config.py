"""Central configuration for the FinSent platform.

Values are read from environment variables (see .env.example) with sensible
defaults so the project runs out of the box for local development.
"""
from __future__ import annotations

import os
from pathlib import Path

# Load variables from a local .env file (if present) into the environment,
# so FINNHUB_API_KEY and friends are picked up automatically.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is optional; env vars set another way still work.
    pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Full path to the SQLite database file.
DB_PATH = Path(os.getenv("FINSENT_DB_PATH", DATA_DIR / "finsent.db"))

# ---------------------------------------------------------------------------
# Data ingestion settings
# ---------------------------------------------------------------------------
# Finnhub free-tier API key. Get one at https://finnhub.io/ (no cost).
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

# How many days of historical price data to pull on a full ingest.
PRICE_LOOKBACK_DAYS = int(os.getenv("FINSENT_PRICE_LOOKBACK_DAYS", "365"))

# How many days of news to request per ticker (Finnhub caps free-tier history).
NEWS_LOOKBACK_DAYS = int(os.getenv("FINSENT_NEWS_LOOKBACK_DAYS", "365"))

# Finnhub caps each company-news response at ~250 items and returns the most
# recent ones, so a single wide request leaves most of the timeline empty.
# We page through history in chunks of this many days, one request per chunk.
NEWS_CHUNK_DAYS = int(os.getenv("FINSENT_NEWS_CHUNK_DAYS", "14"))

# Polite delay (seconds) between external API calls to respect rate limits.
REQUEST_DELAY_SECONDS = float(os.getenv("FINSENT_REQUEST_DELAY", "1.0"))