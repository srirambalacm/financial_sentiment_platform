import { useApi } from "../useApi";
import { getHeadlines } from "../api/client";
import { formatDate, formatScore } from "../format";

interface HeadlineListProps {
  symbol: string;
}

const LABEL_STYLES: Record<string, string> = {
  positive: "bg-green-950/60 text-green-300 border-green-800",
  negative: "bg-red-950/60 text-red-300 border-red-800",
  neutral: "bg-slate-800 text-slate-300 border-slate-700",
};

function SentimentPill({ label }: { label: string }) {
  const style = LABEL_STYLES[label] ?? LABEL_STYLES.neutral;
  return (
    <span
      className={`inline-block rounded-full border px-2 py-0.5 text-xs capitalize ${style}`}
    >
      {label}
    </span>
  );
}

export default function HeadlineList({ symbol }: HeadlineListProps) {
  const [state, retry] = useApi(() => getHeadlines(symbol, 20), [symbol]);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">
        Recent headlines — {symbol}
      </h2>

      {state.status === "loading" && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 animate-pulse rounded bg-slate-800" />
          ))}
        </div>
      )}

      {state.status === "error" && (
        <div className="flex flex-col items-start gap-2 text-sm text-red-300">
          <span>Couldn't load headlines: {state.message}</span>
          <button
            onClick={retry}
            className="rounded border border-red-800 px-3 py-1 text-red-200 hover:bg-red-900/40"
          >
            Retry
          </button>
        </div>
      )}

      {state.status === "success" && state.data.length === 0 && (
        <p className="text-sm text-slate-500">
          No headlines found for {symbol}.
        </p>
      )}

      {state.status === "success" && state.data.length > 0 && (
        <ul className="divide-y divide-slate-800">
          {state.data.map((h, i) => (
            <li key={i} className="flex flex-wrap items-start gap-2 py-2.5">
              <SentimentPill label={h.sentiment_label} />
              <span className="text-xs text-slate-500">
                {formatScore(h.sentiment_score)}
              </span>
              {!h.is_relevant && (
                <span
                  className="rounded-full border border-amber-800 bg-amber-950/50 px-2 py-0.5 text-xs text-amber-300"
                  title="This headline was scored but does not appear to be about the tagged company"
                >
                  off-topic
                </span>
              )}
              <a
                href={h.url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 flex-1 basis-64 text-sm text-slate-200 underline decoration-slate-600 hover:decoration-slate-300"
              >
                {h.headline}
              </a>
              <span className="ml-auto whitespace-nowrap text-xs text-slate-500">
                {h.source} · {formatDate(h.published_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
