"""FinSent HTTP API.

Serves the ingested corpus and the evaluation results to the dashboard.

Design notes
------------
* Read-only. The API never triggers ingestion or model inference; those are
  batch jobs run from `scripts/`. An HTTP handler that could kick off 40K
  transformer inferences is a denial-of-service waiting to happen.
* The expensive evaluation endpoint is served from a TTL cache, so the first
  request pays the cost and subsequent ones are instant.
* CORS is open by default for local development. Set FINSENT_CORS_ORIGINS to a
  comma-separated list to restrict it in deployment.

Run locally:
    uvicorn api.main:app --reload
Then open http://127.0.0.1:8000/docs for interactive documentation.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api import services
from api.cache import cache
from api.models import (
    BenchmarkOut,
    CorpusStats,
    EvaluationOut,
    HeadlineOut,
    TickerOut,
    TimeSeriesOut,
)
from src.tickers import symbols

logger = logging.getLogger(__name__)

app = FastAPI(
    title="FinSent API",
    version="1.0.0",
    description=(
        "Financial news sentiment platform. Serves the ingested corpus, "
        "per-ticker price and sentiment series, and the out-of-sample "
        "evaluation of whether the sentiment signal predicts returns."
    ),
)

_origins = os.getenv("FINSENT_CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins == "*" else [o.strip() for o in _origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

VALID_SYMBOLS = set(symbols())


def _require_symbol(symbol: str) -> str:
    """Validate a path symbol against the known universe."""
    upper = symbol.upper()
    if upper not in VALID_SYMBOLS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown ticker '{symbol}'. See /api/tickers for the universe.",
        )
    return upper


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness probe. Cheap by design — no database access."""
    return {"status": "ok"}


@app.get("/api/benchmark", response_model=BenchmarkOut, tags=["meta"])
def benchmark() -> dict:
    """The recorded FinBERT benchmark on Financial PhraseBank."""
    return services.BENCHMARK


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------
@app.get("/api/stats", response_model=CorpusStats, tags=["corpus"])
def stats() -> dict:
    """Corpus-wide counts and the sentiment distribution."""
    return cache.get_or_compute("stats", services.get_stats)


@app.get("/api/tickers", response_model=list[TickerOut], tags=["corpus"])
def tickers() -> list[dict]:
    """The tracked universe, with scored-headline counts."""
    return cache.get_or_compute("tickers", services.list_tickers)


@app.get(
    "/api/tickers/{symbol}/timeseries",
    response_model=TimeSeriesOut,
    tags=["corpus"],
)
def timeseries(
    symbol: str,
    days: int = Query(180, ge=1, le=2000, description="Most recent N sessions"),
    relevant_only: bool = Query(True, description="Use relevance-filtered headlines"),
) -> dict:
    """Aligned price and daily sentiment for one ticker."""
    sym = _require_symbol(symbol)
    key = f"ts:{sym}:{days}:{relevant_only}"
    return cache.get_or_compute(
        key, lambda: services.get_timeseries(sym, days=days, relevant_only=relevant_only)
    )


@app.get(
    "/api/tickers/{symbol}/headlines",
    response_model=list[HeadlineOut],
    tags=["corpus"],
)
def headlines(
    symbol: str,
    limit: int = Query(20, ge=1, le=200),
    relevant_only: bool = Query(False),
) -> list[dict]:
    """Most recent scored headlines for one ticker."""
    sym = _require_symbol(symbol)
    key = f"hl:{sym}:{limit}:{relevant_only}"
    return cache.get_or_compute(
        key, lambda: services.get_headlines(sym, limit=limit, relevant_only=relevant_only)
    )


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
@app.get("/api/evaluation", response_model=EvaluationOut, tags=["evaluation"])
def evaluation(
    train_frac: float = Query(0.6, gt=0.1, lt=0.95),
    cost_bps: float = Query(5.0, ge=0.0, le=100.0),
    relevant_only: bool = Query(True),
) -> dict:
    """Out-of-sample evaluation of the sentiment signal.

    Expensive on a cache miss (builds the full panel and runs a parameter
    search), then served from memory for an hour.
    """
    key = f"eval:{train_frac}:{cost_bps}:{relevant_only}"
    try:
        return cache.get_or_compute(
            key,
            lambda: services.compute_evaluation(
                train_frac=train_frac,
                cost_bps=cost_bps,
                relevant_only=relevant_only,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/cache", tags=["meta"])
def cache_stats() -> dict:
    """Cache diagnostics, useful when the dashboard looks stale."""
    return cache.stats()