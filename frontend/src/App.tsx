import { useState } from "react";
import { useApi } from "./useApi";
import {
  getStats,
  getTickers,
  getEvaluation,
  getBenchmark,
} from "./api/client";
import StatCard, { StatCardSkeleton } from "./components/StatCard";
import VerdictBanner from "./components/VerdictBanner";
import TickerSelector from "./components/TickerSelector";
import PriceSentimentChart from "./components/PriceSentimentChart";
import HeadlineList from "./components/HeadlineList";
import EvaluationPanel from "./components/EvaluationPanel";
import MethodologyNote from "./components/MethodologyNote";
import { formatPercent } from "./format";

export default function App() {
  const [selectedTicker, setSelectedTicker] = useState("AAPL");

  const [statsState, retryStats] = useApi(() => getStats(), []);
  const [tickersState, retryTickers] = useApi(() => getTickers(), []);
  const [evaluationState, retryEvaluation] = useApi(() => getEvaluation(), []);
  const [benchmarkState, retryBenchmark] = useApi(() => getBenchmark(), []);

  const backendUnreachable = [
    statsState,
    tickersState,
    evaluationState,
    benchmarkState,
  ].some((s) => s.status === "error" && s.unreachable);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-slate-100">FinSent</h1>
        <p className="mt-1 text-sm text-slate-400">
          Does financial news sentiment predict returns?
        </p>
      </header>

      {backendUnreachable && (
        <div className="mb-6 rounded-lg border border-red-800 bg-red-950/40 p-4 text-sm text-red-200">
          Backend not running — start it with{" "}
          <code className="rounded bg-red-900/40 px-1.5 py-0.5 font-mono text-red-100">
            uvicorn api.main:app --reload
          </code>
        </div>
      )}

      <div className="space-y-6">
        <VerdictBanner state={evaluationState} onRetry={retryEvaluation} />

        <section
          aria-label="Summary statistics"
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
        >
          {statsState.status === "loading" || benchmarkState.status === "loading" ? (
            Array.from({ length: 5 }).map((_, i) => <StatCardSkeleton key={i} />)
          ) : statsState.status === "error" ? (
            <div className="col-span-full rounded-lg border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-300">
              Couldn't load stats: {statsState.message}{" "}
              <button onClick={retryStats} className="ml-2 underline">
                Retry
              </button>
            </div>
          ) : benchmarkState.status === "error" ? (
            <div className="col-span-full rounded-lg border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-300">
              Couldn't load benchmark: {benchmarkState.message}{" "}
              <button onClick={retryBenchmark} className="ml-2 underline">
                Retry
              </button>
            </div>
          ) : (
            <>
              <StatCard
                label="Headlines"
                value={statsState.data.n_headlines.toLocaleString()}
              />
              <StatCard
                label="Tickers tracked"
                value={statsState.data.n_tickers.toLocaleString()}
              />
              <StatCard
                label="FinBERT accuracy"
                value={formatPercent(benchmarkState.data.accuracy)}
                hint="Financial PhraseBank benchmark"
              />
              <StatCard
                label="Macro F1"
                value={benchmarkState.data.macro_f1.toFixed(3)}
                hint="Financial PhraseBank benchmark"
              />
              <StatCard
                label="Relevance retention"
                value={formatPercent(statsState.data.relevant_pct / 100)}
                hint="Headlines that mention the tagged company"
              />
            </>
          )}
        </section>

        <section aria-label="Ticker selection">
          <TickerSelector
            state={tickersState}
            selected={selectedTicker}
            onSelect={setSelectedTicker}
            onRetry={retryTickers}
          />
        </section>

        <PriceSentimentChart symbol={selectedTicker} />

        <EvaluationPanel state={evaluationState} onRetry={retryEvaluation} />

        <HeadlineList symbol={selectedTicker} />

        <MethodologyNote />
      </div>
    </div>
  );
}
