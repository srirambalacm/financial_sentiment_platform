import { useState } from "react";

const CONTROLS = [
  "One-day lookahead lag between sentiment signal and the return it predicts, to avoid look-ahead bias.",
  "Chronological train/test split — parameters selected on the training window only, evaluated once on held-out sessions.",
  "5 bps transaction costs applied to simulated performance.",
  "Cross-sectional ranking of tickers by sentiment each session, rather than an absolute threshold.",
  "Relevance filtering — headlines not judged to be about the tagged company are excluded from the sentiment signal.",
];

export default function MethodologyNote() {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between text-left text-sm font-semibold text-slate-200"
      >
        Methodology &amp; controls
        <span className="text-slate-500">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-slate-400">
          {CONTROLS.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
