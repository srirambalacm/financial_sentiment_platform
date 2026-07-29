import type { AsyncState } from "../useApi";
import type { Ticker } from "../api/client";

interface TickerSelectorProps {
  state: AsyncState<Ticker[]>;
  selected: string;
  onSelect: (symbol: string) => void;
  onRetry: () => void;
}

export default function TickerSelector({
  state,
  selected,
  onSelect,
  onRetry,
}: TickerSelectorProps) {
  if (state.status === "loading") {
    return (
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="h-8 w-20 animate-pulse rounded-full bg-slate-800"
          />
        ))}
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="rounded border border-red-900/50 bg-red-950/30 p-3 text-sm text-red-300">
        Couldn't load tickers: {state.message}{" "}
        <button
          onClick={onRetry}
          className="ml-2 underline hover:text-red-200"
        >
          Retry
        </button>
      </div>
    );
  }

  if (state.data.length === 0) {
    return (
      <div className="text-sm text-slate-500">No tickers available.</div>
    );
  }

  return (
    <div>
      <label htmlFor="ticker-selector" className="sr-only">
        Select a ticker
      </label>
      <div
        id="ticker-selector"
        role="listbox"
        aria-label="Select a ticker"
        className="flex flex-wrap gap-2"
      >
        {state.data.map((t) => {
          const isSelected = t.symbol === selected;
          return (
            <button
              key={t.symbol}
              role="option"
              aria-selected={isSelected}
              onClick={() => onSelect(t.symbol)}
              className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                isSelected
                  ? "border-teal-600 bg-teal-900/40 text-teal-200"
                  : "border-slate-700 bg-slate-900/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800"
              }`}
              title={t.name}
            >
              {t.symbol}{" "}
              <span className="text-slate-500">({t.headline_count})</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
