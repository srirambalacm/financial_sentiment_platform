// Typed fetch wrappers for the FinSent FastAPI backend.
// All shapes below were verified against live responses from
// http://127.0.0.1:8000 before being written.

export interface SentimentDistributionBucket {
  label: string;
  count: number;
  share: number;
  avg_score: number;
  avg_confidence: number;
}

export interface Stats {
  n_tickers: number;
  n_prices: number;
  n_headlines: number;
  n_scored: number;
  scored_pct: number;
  n_relevant: number;
  relevant_pct: number;
  distribution: SentimentDistributionBucket[];
}

export interface Ticker {
  symbol: string;
  name: string;
  sector: string;
  headline_count: number;
}

export interface TimeseriesPoint {
  date: string;
  close: number;
  sentiment: number | null;
  headline_count: number;
}

export interface Timeseries {
  symbol: string;
  n_sessions: number;
  points: TimeseriesPoint[];
}

export interface Headline {
  headline: string;
  source: string;
  url: string;
  published_at: string;
  sentiment_label: string;
  sentiment_score: number;
  sentiment_confidence: number;
  is_relevant: boolean;
}

export interface ICStats {
  mean_ic: number;
  t_stat: number;
  p_value: number;
  n_days: number;
  hit_rate: number;
  significant: boolean;
}

export interface Coverage {
  total_sessions: number;
  covered_sessions: number;
  coverage_pct: number;
  first_covered: string;
  last_covered: string;
}

export interface PerformanceRow {
  label: string;
  total_return: number;
  annualized_return: number;
  annualized_volatility: number;
  sharpe_ratio: number;
  max_drawdown: number;
  n_days: number;
}

export interface Evaluation {
  coverage: Coverage;
  ic_full_sample: ICStats;
  ic_out_of_sample: ICStats;
  performance: PerformanceRow[];
  selected_window: number;
  selected_top_n: number;
  train_sessions: number;
  test_sessions: number;
  verdict: string;
}

export interface Benchmark {
  model: string;
  dataset: string;
  subset: string;
  n_sentences: number;
  accuracy: number;
  macro_f1: number;
}

/** Thrown for any failed request. `unreachable` is true when the network
 * request itself failed (backend down), as opposed to a non-2xx response. */
export class ApiError extends Error {
  unreachable: boolean;

  constructor(message: string, unreachable: boolean) {
    super(message);
    this.name = "ApiError";
    this.unreachable = unreachable;
  }
}

async function getJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path);
  } catch {
    throw new ApiError(
      "Backend not running — start it with `uvicorn api.main:app --reload`",
      true
    );
  }

  if (!response.ok) {
    throw new ApiError(
      `Request to ${path} failed: ${response.status} ${response.statusText}`,
      false
    );
  }

  return (await response.json()) as T;
}

export function getStats(): Promise<Stats> {
  return getJson<Stats>("/api/stats");
}

export function getTickers(): Promise<Ticker[]> {
  return getJson<Ticker[]>("/api/tickers");
}

export function getTimeseries(
  symbol: string,
  days: number,
  relevantOnly = true
): Promise<Timeseries> {
  const params = new URLSearchParams({
    days: String(days),
    relevant_only: String(relevantOnly),
  });
  return getJson<Timeseries>(
    `/api/tickers/${encodeURIComponent(symbol)}/timeseries?${params.toString()}`
  );
}

export function getHeadlines(
  symbol: string,
  limit = 20
): Promise<Headline[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return getJson<Headline[]>(
    `/api/tickers/${encodeURIComponent(symbol)}/headlines?${params.toString()}`
  );
}

export function getEvaluation(): Promise<Evaluation> {
  return getJson<Evaluation>("/api/evaluation");
}

export function getBenchmark(): Promise<Benchmark> {
  return getJson<Benchmark>("/api/benchmark");
}
