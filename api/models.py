"""Response schemas for the FinSent API.

Declaring explicit Pydantic models rather than returning raw dicts buys three
things: FastAPI generates accurate OpenAPI docs from them, responses are
validated before they leave the server (so a schema drift becomes a loud
error instead of a silently malformed payload), and the frontend has a
contract it can rely on.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TickerOut(BaseModel):
    symbol: str
    name: str
    sector: str
    headline_count: int = Field(..., description="Scored headlines for this ticker")


class PricePoint(BaseModel):
    date: str
    close: float
    sentiment: Optional[float] = Field(
        None, description="Count-weighted mean sentiment for that session, if any"
    )
    headline_count: int = 0


class TimeSeriesOut(BaseModel):
    symbol: str
    points: list[PricePoint]
    n_sessions: int


class HeadlineOut(BaseModel):
    headline: str
    source: Optional[str] = None
    url: Optional[str] = None
    published_at: str
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    sentiment_confidence: Optional[float] = None
    is_relevant: Optional[bool] = None


class SentimentDistribution(BaseModel):
    label: str
    count: int
    share: float
    avg_score: float
    avg_confidence: float


class CorpusStats(BaseModel):
    n_tickers: int
    n_prices: int
    n_headlines: int
    n_scored: int
    scored_pct: float
    n_relevant: int
    relevant_pct: float
    distribution: list[SentimentDistribution]


class ICOut(BaseModel):
    mean_ic: float
    t_stat: float
    p_value: float
    n_days: int
    hit_rate: float
    significant: bool = Field(..., description="p < 0.05")


class PerformanceOut(BaseModel):
    label: str
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    n_days: int


class CoverageOut(BaseModel):
    total_sessions: int
    covered_sessions: int
    coverage_pct: float
    first_covered: Optional[str] = None
    last_covered: Optional[str] = None


class EvaluationOut(BaseModel):
    """The headline scientific result, as served to the dashboard."""

    coverage: CoverageOut
    ic_full_sample: ICOut
    ic_out_of_sample: ICOut
    performance: list[PerformanceOut]
    selected_window: int
    selected_top_n: int
    train_sessions: int
    test_sessions: int
    verdict: str = Field(..., description="Plain-language summary of the finding")


class BenchmarkOut(BaseModel):
    """Static record of the FinBERT model benchmark (see scripts/benchmark_model.py)."""

    model: str
    dataset: str
    subset: str
    n_sentences: int
    accuracy: float
    macro_f1: float