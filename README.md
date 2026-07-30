![CI](https://github.com/srirambalacm/financial_sentiment_platform/actions/workflows/ci.yml/badge.svg)
# FinSent — Financial News Sentiment Signal Platform

An end-to-end pipeline that ingests a year of financial news, scores it with a
transformer model, and rigorously tests whether the resulting sentiment signal
predicts equity returns.

**Headline finding: it does not.** Over 246 trading sessions and 120K
headlines, the signal's information coefficient is **-0.006 (p = 0.63)** —
statistically indistinguishable from zero. That negative result is the
project's main output, and the evaluation machinery built to establish it
credibly is the point.

---

## Problem

Financial news arrives faster than any human can read it, and "sentiment
predicts price" is an intuitive, widely repeated claim. It is also rarely
tested honestly: most public analyses tune parameters until a backtest looks
profitable, report the in-sample number, and quietly omit transaction costs
and lookahead controls.

The question this project answers is narrower and more useful: **does news
sentiment carry measurable predictive information about next-day returns for
large-cap US equities — and how would you know?**

## Action

| Stage | What was built |
|---|---|
| **Ingestion** | 120,375 headlines + 6,647 daily OHLCV bars across 25 S&P 500 tickers, ~1 year (Aug 2025 – Jul 2026), into a normalized SQLite store with content-hash deduplication. |
| **Scoring** | FinBERT (`ProsusAI/finbert`) batch inference over 51,892 headlines, producing a signed sentiment score and confidence per headline. |
| **Model validation** | Benchmarked FinBERT on the Financial PhraseBank corpus (3,453 human-annotated sentences, 75%-agreement subset). |
| **Data-quality audit** | Built a relevance filter after discovering the news API tags stories loosely. |
| **Evaluation** | Cross-sectional information coefficient with significance testing, a dollar-neutral long/short backtest, strict lookahead controls, transaction costs, and a chronological train/test split. |

## Result

**Model quality — FinBERT on Financial PhraseBank (75% agreement, n=3,453):**

| Metric | Value |
|---|---|
| Accuracy | **94.73%** |
| Macro F1 | **0.9365** |

Per-class F1: negative 0.918, neutral 0.961, positive 0.931. Macro F1 is
reported alongside accuracy because the classes are imbalanced (2,146 neutral
vs 420 negative), and plain accuracy would mask weak minority-class
performance.

**Data quality — relevance audit:**

Only **37.0%** of headlines (44,554 / 120,375) actually mention the company
they were tagged to. The news API attaches stories to tickers generously: an
Entergy story arrived tagged to META, a SpaceX story to ORCL. Per-ticker
retention ranged from 12.2% (META) to 60.3% (NFLX). This is a measured
property of the data source, not an estimate.

**Signal quality — the actual finding:**

| Measurement | Value | Interpretation |
|---|---|---|
| Information coefficient (full sample, 245 days) | **-0.006** (t = -0.49, p = 0.63) | No predictive information |
| IC, relevance-filtered | -0.006 (t = -0.46, p = 0.65) | Filtering does not rescue it |
| IC, held-out test window (98 days) | -0.006 (t = -0.26, p = 0.79) | Confirms out-of-sample |
| Days with positive IC | 49% | A coin flip |

**Strategy performance — long/short, top-3 vs bottom-3 by sentiment rank:**

| | Return | Sharpe | Vol | Max DD |
|---|---|---|---|---|
| In-sample (147 sessions) | +3.19% | 0.34 | 23.8% | -11.6% |
| **Out-of-sample (98 sessions)** | **-9.36%** | **-1.04** | 22.0% | -11.9% |
| Buy & hold (same window) | +5.23% | 1.15 | 12.0% | -5.6% |

The in-sample Sharpe of 0.34 was the best of 15 parameter combinations. It did
not survive contact with held-out data. That decay is the entire reason the
train/test split exists.

## Why this is the expected result

These 25 tickers are among the most closely watched securities in the world.
Thousands of professionals with faster data and better models trade these
headlines within milliseconds of publication. A signal built from a free news
API, an off-the-shelf model, and daily-frequency data should not find alpha
there — and if it had, the correct first response would have been to search
for the bug, not to celebrate.

## How the evaluation avoids fooling itself

Five controls, each of which materially changes the answer:

1. **Lookahead guard.** Day *D*'s sentiment is applied to day *D+1*'s return.
   Weekend news maps forward to the next session, never backward. Writing the
   test for this caught a real bug: positions were being aligned to the
   returns index *before* being shifted, silently discarding the first
   session's position.
2. **Chronological train/test split.** Parameters were selected on the first
   147 sessions and evaluated once on the remaining 98. The split is by date,
   never random — shuffling time-series rows leaks the future.
3. **Transaction costs.** 5bps charged on every position change, so a signal
   that churns daily is penalized for it.
4. **Cross-sectional ranking.** Replaced an absolute sentiment threshold after
   diagnosing that it was mis-calibrated per ticker: densely covered mega-caps
   average toward the corpus mean (+0.03) and never cleared a +0.10 cutoff,
   producing ~3% market exposure and a meaningless backtest.
5. **Two-sided validation of the harness itself.** On synthetic data with a
   planted signal, the pipeline recovers IC ≈ +0.14. On random noise, it
   reports IC ≈ 0 with p > 0.05. It can find a signal that exists and does not
   hallucinate one that doesn't.

## Architecture

```
  yfinance ──▶ ingest_prices ─┐
                              ├─▶ SQLite ──▶ FinBERT scorer ──▶ relevance filter
  Finnhub  ──▶ ingest_news  ──┘   (tickers·prices·headlines)          │
             (paginated, 27                                            ▼
              windows/ticker)                    cross-sectional panel (date × ticker)
                                                                       │
                                              ┌────────────────────────┴───────┐
                                              ▼                                ▼
                                    information coefficient          long/short backtest
                                    (+ significance test)         (costs, lookahead guard)
```

## Engineering notes

* **Paginated ingestion.** The news API caps each response at ~250 items and
  returns the most recent matches, so a single wide request yields headlines
  clustered in the last few weeks while reporting healthy row counts. The
  first version of this project hit exactly that trap: 11,579 headlines
  covering only 35 distinct sessions, which made the training window entirely
  newsless and every parameter combination return exactly 0.00%. Splitting the
  range into 27 fortnightly windows per ticker raised coverage from 13% to
  **92.5%** of the price calendar.
* **Coverage guard.** The evaluation now refuses to report on a panel whose
  sessions lack news, rather than silently averaging in zeros.
* **Resumability.** Ingestion deduplicates on a content hash, scoring only
  touches unscored rows, and relevance tagging is idempotent — so every stage
  can be interrupted and re-run without corruption or double-counting.
* **Lazy model loading.** `torch`/`transformers` are imported on first use, so
  the 84-test suite runs in ~4 seconds without the ML stack installed.

## Test suite

84 tests. The load-bearing ones assert properties rather than outputs:

* Random sentiment must produce a statistically insignificant IC.
* A signal that "predicts" the same day's move must earn nothing after the
  one-day lag.
* Ingestion windows must tile the date range with no gaps and no overlaps.
* Long/short weights must be exactly dollar-neutral.

```bash
pytest    # 84 passed
```

CI installs `requirements-ci.txt`, which omits torch, transformers,
scikit-learn and yfinance. The suite does not need them — `src/sentiment.py`
imports torch lazily inside the model loader — which cuts the CI install from
minutes and ~2GB to a few seconds.

## Reproducing

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt
cp .env.example .env                               # add a free Finnhub key

python -m scripts.check_api                        # verify key + history depth
python -m scripts.run_ingest                       # ~20 min, 675 requests
python -m scripts.tag_relevance
python -m scripts.score_headlines --relevant-only  # ~25 min on CPU
python -m scripts.benchmark_model --config sentences_75agree
python -m scripts.run_evaluation --relevant-only
```

## Serving layer

A read-only FastAPI backend exposes the corpus and the evaluation results, and
a React/TypeScript dashboard renders them.

| Endpoint | Purpose |
|---|---|
| `/api/stats` | Corpus counts and sentiment distribution |
| `/api/tickers` | Universe with scored-headline counts |
| `/api/tickers/{symbol}/timeseries` | Aligned price and daily sentiment |
| `/api/tickers/{symbol}/headlines` | Recent scored headlines |
| `/api/evaluation` | IC, coverage, and out-of-sample performance |
| `/api/benchmark` | Recorded FinBERT benchmark |

The evaluation endpoint builds the full panel and runs the parameter search —
**3.5s cold, 2ms cached** (~1,600x), via an in-process TTL cache. The API never
runs model inference; scoring stays a batch job in `scripts/`, so an HTTP
handler can never trigger 40K transformer passes.

```bash
uvicorn api.main:app --reload     # http://127.0.0.1:8000/docs
cd frontend && npm install && npm run dev
```

The dashboard leads with the null result rather than burying it, and tags
headlines that failed the relevance filter as *off-topic* — making the 37%
retention finding visible rather than merely asserted.

## Limitations

* **Daily frequency.** News moves prices in seconds; a daily bar cannot
  capture intraday reaction. Any real signal likely lives at a horizon this
  data cannot see.
* **Headline text only.** Article bodies were not ingested, so the model sees
  a fraction of the available information.
* **Relevance filter is precision-oriented.** It matches company aliases and
  will miss oblique references ("the iPhone maker's supplier"); "visa" also
  matches travel-visa stories.
* **Response truncation.** Each 14-day window returns ~245 of a possible ~250
  items, so the densest news days are likely partially sampled.
* **Single universe, single period.** 25 large-caps over one year. The result
  may not generalize to small-caps, other sectors, or other regimes.
* **Multiple comparisons.** 15 parameter combinations were evaluated in-sample;
  the reported out-of-sample figure is the single selected configuration.

## Roadmap

- [x] **Phase 1 — Data foundation:** ingestion, storage, deduplication, tests
- [x] **Phase 2 — ML core:** FinBERT scoring + PhraseBank benchmark
- [x] **Phase 3 — Evaluation:** IC, relevance filter, lookahead controls, train/test split, long/short backtest
- [x] **Phase 4 — API + dashboard:** FastAPI backend (cached evaluation endpoint) + React/TypeScript dashboard
- [x] **Phase 5 — Ship:** GitHub Actions CI + deployment (see `DEPLOYMENT.md`)

## Disclaimer

A technical exercise in data engineering, machine learning, and quantitative
evaluation. Nothing here is investment advice. The backtests are historical
analyses, and the headline finding is explicitly that the signal studied did
**not** predict returns.
