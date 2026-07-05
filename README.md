# FinSent — Financial News Sentiment Signal Platform

A full-stack platform that ingests financial news, scores it with a transformer
model (FinBERT), and backtests whether news sentiment predicts price movement.

> **Status:** Phase 1 of 5 — Data Foundation ✅

---

## Problem

Thousands of financial headlines are published every day. Retail investors have
no practical way to quantify how that flood of news relates to actual price
movement — sentiment is read anecdotally, one headline at a time, with no
measurement of whether it carries any predictive signal.

## Action

FinSent builds a reproducible pipeline that:

1. **Ingests** daily price data and company news for a curated universe of
   ~25 large-cap S&P 500 tickers into a normalized SQLite store.
2. **Scores** each headline with FinBERT and benchmarks the model on the
   Financial PhraseBank dataset *(Phase 2)*.
3. **Backtests** a sentiment-driven trading signal against a buy-and-hold
   baseline, controlling for lookahead bias *(Phase 3)*.
4. **Serves** the results through a FastAPI backend and a React dashboard
   *(Phases 4–5)*.

## Result

_Benchmark and backtest numbers will be filled in as later phases land._

---

## Architecture

```
              ┌─────────────┐     ┌──────────────┐
 Yahoo Finance│  yfinance   │     │   Finnhub    │ Company news
   (prices) ──▶ ingest_prices│    │ ingest_news  ◀── (headlines)
              └──────┬──────┘     └──────┬───────┘
                     │                   │
                     ▼                   ▼
              ┌──────────────────────────────┐
              │   SQLite (repository layer)   │
              │  tickers · prices · headlines │
              └──────────────────────────────┘
                     │
                     ▼  (Phases 2–5)
        FinBERT scoring → backtest → FastAPI → React dashboard
```

## Data model

| Table       | Purpose                                             |
|-------------|-----------------------------------------------------|
| `tickers`   | The tracked stock universe (symbol, name, sector).  |
| `prices`    | Daily OHLCV bars, unique per `(symbol, date)`.       |
| `headlines` | Deduplicated news, with nullable sentiment columns the Phase 2 scorer fills in. |

## Getting started

```bash
# 1. Clone and enter the project
git clone <your-repo-url> && cd finsent

# 2. Create a virtual environment and install deps
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. (Optional, for news) add your free Finnhub key
cp .env.example .env        # then edit .env and paste your key

# 4. Run the ingest
python -m scripts.run_ingest --prices-only   # prices only, no key needed
python -m scripts.run_ingest                 # prices + news (needs key)
```

## Running the tests

```bash
pytest            # runs the data-layer test suite
```

## Project layout

```
finsent/
├── config.py             # env-driven configuration
├── src/
│   ├── tickers.py        # the ticker universe
│   ├── database.py       # schema + all DB reads/writes (repository layer)
│   ├── ingest_prices.py  # Yahoo Finance price ingestion
│   └── ingest_news.py    # Finnhub news ingestion
├── scripts/
│   └── run_ingest.py     # end-to-end ingest orchestration
└── tests/
    └── test_database.py  # data-layer tests
```

## Roadmap

- [x] **Phase 1 — Data foundation:** ingestion pipeline + storage + tests
- [ ] **Phase 2 — ML core:** FinBERT scoring + PhraseBank benchmark
- [ ] **Phase 3 — Backtest:** sentiment signal vs. buy-and-hold (Sharpe, returns)
- [ ] **Phase 4 — API + frontend:** FastAPI endpoints + React dashboard
- [ ] **Phase 5 — Ship:** deployment + CI + polished docs

## Disclaimer

This project is a technical and educational exercise in data engineering and
machine learning. Nothing here is investment advice, and the backtests are
historical analyses, not predictions of future returns.
