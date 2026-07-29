import type { AsyncState } from "../useApi";
import type { Evaluation, ICStats, PerformanceRow } from "../api/client";
import {
  formatIC,
  formatPValue,
  formatPercent,
  formatSignedPercent,
  formatSharpe,
} from "../format";

interface EvaluationPanelProps {
  state: AsyncState<Evaluation>;
  onRetry: () => void;
}

function ICRow({ name, ic }: { name: string; ic: ICStats }) {
  return (
    <tr className="border-b border-slate-800 last:border-0">
      <td className="py-2 pr-4 text-slate-300">{name}</td>
      <td className="py-2 pr-4 tabular-nums text-slate-200">
        {formatIC(ic.mean_ic)}
      </td>
      <td className="py-2 pr-4 tabular-nums text-slate-200">
        {ic.t_stat.toFixed(2)}
      </td>
      <td className="py-2 pr-4 tabular-nums text-slate-200">
        {formatPValue(ic.p_value)}
      </td>
      <td className="py-2 pr-4 tabular-nums text-slate-200">{ic.n_days}</td>
      <td className="py-2 pr-4 tabular-nums text-slate-200">
        {formatPercent(ic.hit_rate)}
      </td>
      <td className="py-2 pr-4">
        {ic.significant ? (
          <span className="rounded-full border border-slate-600 bg-slate-800 px-2 py-0.5 text-xs text-slate-200">
            Significant
          </span>
        ) : (
          <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-xs text-slate-400">
            Not statistically significant
          </span>
        )}
      </td>
    </tr>
  );
}

function PerformanceTableRow({ row }: { row: PerformanceRow }) {
  const returnClass =
    row.total_return > 0
      ? "text-green-400"
      : row.total_return < 0
      ? "text-red-400"
      : "text-slate-300";
  const drawdownClass =
    row.max_drawdown < 0 ? "text-red-400" : "text-slate-300";

  return (
    <tr className="border-b border-slate-800 last:border-0">
      <td className="py-2 pr-4 text-slate-300">{row.label}</td>
      <td className={`py-2 pr-4 tabular-nums ${returnClass}`}>
        {formatSignedPercent(row.total_return)}
      </td>
      <td className={`py-2 pr-4 tabular-nums ${returnClass}`}>
        {formatSignedPercent(row.annualized_return)}
      </td>
      <td className="py-2 pr-4 tabular-nums text-slate-200">
        {formatPercent(row.annualized_volatility)}
      </td>
      <td className="py-2 pr-4 tabular-nums text-slate-200">
        {formatSharpe(row.sharpe_ratio)}
      </td>
      <td className={`py-2 pr-4 tabular-nums ${drawdownClass}`}>
        {formatSignedPercent(row.max_drawdown)}
      </td>
      <td className="py-2 pr-4 tabular-nums text-slate-200">{row.n_days}</td>
    </tr>
  );
}

export default function EvaluationPanel({
  state,
  onRetry,
}: EvaluationPanelProps) {
  if (state.status === "loading") {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-2 h-4 w-40 animate-pulse rounded bg-slate-800" />
        <div className="h-32 animate-pulse rounded bg-slate-800" />
        <p className="mt-2 text-xs text-slate-500">
          Computing evaluation (first load can take a few seconds)…
        </p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300">
        Couldn't load evaluation results: {state.message}
        <div>
          <button
            onClick={onRetry}
            className="mt-2 rounded border border-red-800 px-3 py-1 text-red-200 hover:bg-red-900/40"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const { ic_full_sample, ic_out_of_sample, performance, train_sessions, test_sessions } =
    state.data;

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">
        Information coefficient
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-xs uppercase tracking-wide text-slate-400">
              <th className="py-2 pr-4 font-medium">Sample</th>
              <th className="py-2 pr-4 font-medium">IC</th>
              <th className="py-2 pr-4 font-medium">t-stat</th>
              <th className="py-2 pr-4 font-medium">p-value</th>
              <th className="py-2 pr-4 font-medium">Days</th>
              <th className="py-2 pr-4 font-medium">Hit rate</th>
              <th className="py-2 pr-4 font-medium">Significance</th>
            </tr>
          </thead>
          <tbody>
            <ICRow name="Full sample" ic={ic_full_sample} />
            <ICRow name="Out-of-sample" ic={ic_out_of_sample} />
          </tbody>
        </table>
      </div>

      {performance.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">
          No performance data available.
        </p>
      ) : (
        <>
          <h2 className="mb-3 mt-6 text-sm font-semibold text-slate-200">
            Performance
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">Strategy</th>
                  <th className="py-2 pr-4 font-medium">Total return</th>
                  <th className="py-2 pr-4 font-medium">Annualized return</th>
                  <th className="py-2 pr-4 font-medium">Volatility</th>
                  <th className="py-2 pr-4 font-medium">Sharpe</th>
                  <th className="py-2 pr-4 font-medium">Max drawdown</th>
                  <th className="py-2 pr-4 font-medium">Days</th>
                </tr>
              </thead>
              <tbody>
                {performance.map((row) => (
                  <PerformanceTableRow key={row.label} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <p className="mt-4 text-xs text-slate-500">
        Parameters (window, top-N) were selected on {train_sessions} training
        sessions and evaluated once, unchanged, on {test_sessions} held-out
        test sessions.
      </p>
    </div>
  );
}
