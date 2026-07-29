import type { AsyncState } from "../useApi";
import type { Evaluation } from "../api/client";
import { formatIC, formatPValue } from "../format";

interface VerdictBannerProps {
  state: AsyncState<Evaluation>;
  onRetry: () => void;
}

export default function VerdictBanner({ state, onRetry }: VerdictBannerProps) {
  if (state.status === "loading") {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6 animate-pulse">
        <div className="h-4 w-40 rounded bg-slate-800" />
        <div className="mt-3 h-6 w-full max-w-xl rounded bg-slate-800" />
        <div className="mt-2 h-6 w-2/3 rounded bg-slate-800" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="rounded-lg border border-amber-900/50 bg-amber-950/30 p-6">
        <p className="text-sm text-amber-200">
          Couldn't load the evaluation verdict: {state.message}
        </p>
        <button
          onClick={onRetry}
          className="mt-3 rounded border border-amber-800 px-3 py-1 text-sm text-amber-200 hover:bg-amber-900/40"
        >
          Retry
        </button>
      </div>
    );
  }

  const { verdict, ic_out_of_sample } = state.data;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-6">
      <div className="text-xs uppercase tracking-wide text-slate-400">
        Finding
      </div>
      <p className="mt-2 text-lg leading-relaxed text-slate-100">{verdict}</p>
      <div className="mt-4 flex flex-wrap gap-8">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Information coefficient (out-of-sample)
          </div>
          <div className="text-3xl font-semibold text-slate-100">
            {formatIC(ic_out_of_sample.mean_ic)}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">
            p-value
          </div>
          <div className="text-3xl font-semibold text-slate-100">
            {formatPValue(ic_out_of_sample.p_value)}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Significant?
          </div>
          <div className="text-3xl font-semibold text-slate-100">
            {ic_out_of_sample.significant ? "Yes" : "No"}
          </div>
        </div>
      </div>
    </div>
  );
}
