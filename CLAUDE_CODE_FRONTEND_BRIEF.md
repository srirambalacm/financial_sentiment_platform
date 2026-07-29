# Claude Code brief — FinSent dashboard (Phase 4 frontend)

Paste this whole file to Claude Code from the project root
(`C:\Users\bvksr\Downloads\finsent-phase1\finsent`).

---

## Context

This repo is a financial-news sentiment research platform. Phases 1–3 (data
ingestion, FinBERT scoring, statistical evaluation) and the FastAPI backend
are complete and tested — 84 passing tests. Do not modify anything in `src/`,
`api/`, `scripts/`, or `tests/`.

Your task is **only** to build the React frontend in a new `frontend/`
directory at the repo root.

## The finding the UI must communicate

This project's headline result is a **negative** one: news sentiment showed
**no** predictive power over next-day returns (information coefficient
-0.006, p = 0.63, across 246 trading sessions). The dashboard must present
this honestly and prominently. Do **not** design it like a trading product
that implies profitable signals. It is a research dashboard reporting a null
result, and the credibility of the presentation is the point.

## Backend API (already running)

Start it with `uvicorn api.main:app --reload` → `http://127.0.0.1:8000`.
Interactive docs at `/docs`. All endpoints are GET and CORS is open.

| Endpoint | Returns |
|---|---|
| `/api/stats` | `{n_tickers, n_prices, n_headlines, n_scored, scored_pct, n_relevant, relevant_pct, distribution: [{label, count, share, avg_score, avg_confidence}]}` |
| `/api/tickers` | `[{symbol, name, sector, headline_count}]` |
| `/api/tickers/{symbol}/timeseries?days=180&relevant_only=true` | `{symbol, n_sessions, points: [{date, close, sentiment, headline_count}]}` — `sentiment` may be `null` |
| `/api/tickers/{symbol}/headlines?limit=20` | `[{headline, source, url, published_at, sentiment_label, sentiment_score, sentiment_confidence, is_relevant}]` |
| `/api/evaluation` | `{coverage:{total_sessions, covered_sessions, coverage_pct, first_covered, last_covered}, ic_full_sample:{mean_ic, t_stat, p_value, n_days, hit_rate, significant}, ic_out_of_sample:{...}, performance:[{label, total_return, annualized_return, annualized_volatility, sharpe_ratio, max_drawdown, n_days}], selected_window, selected_top_n, train_sessions, test_sessions, verdict}` |
| `/api/benchmark` | `{model, dataset, subset, n_sentences, accuracy, macro_f1}` |

Note: `/api/evaluation` takes ~3–4s on a cold cache, then ~2ms. Show a loading
state for it.

## What to build

**Stack:** Vite + React + TypeScript, Tailwind CSS, Recharts, plain `fetch`.
No routing library — this is a single page. No state library.

```
frontend/
├── src/
│   ├── api/client.ts          # typed fetch wrappers + TS interfaces per endpoint
│   ├── components/
│   │   ├── StatCard.tsx
│   │   ├── VerdictBanner.tsx
│   │   ├── PriceSentimentChart.tsx
│   │   ├── TickerSelector.tsx
│   │   ├── HeadlineList.tsx
│   │   ├── EvaluationPanel.tsx
│   │   └── MethodologyNote.tsx
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── index.html
├── package.json
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
├── vite.config.ts             # proxy /api -> http://127.0.0.1:8000
└── README.md                  # how to run it
```

### Page layout, top to bottom

1. **Header** — "FinSent" title, one-line subtitle: *Does financial news
   sentiment predict returns?*

2. **VerdictBanner** — the most prominent element. Render `verdict` from
   `/api/evaluation`. Style it as a neutral//informational finding (slate or
   amber), **not** as an error and **not** as a success. Include the IC and
   p-value as large figures.

3. **Stat cards row** — from `/api/stats` and `/api/benchmark`: total
   headlines, tickers tracked, FinBERT accuracy (as %), macro F1, and
   relevance-filter retention (`relevant_pct`) with a short label like
   "headlines that mention the tagged company".

4. **TickerSelector** — dropdown or scrollable pill list of all 25 tickers,
   showing symbol and headline count. Default to AAPL.

5. **PriceSentimentChart** — Recharts `ComposedChart` for the selected ticker
   from `/timeseries?days=180`:
   - Line on the left Y axis = `close` (price)
   - Bars on the right Y axis = `sentiment`, green when > 0, red when < 0
   - Skip null sentiment values (use `connectNulls={false}`)
   - Tooltip showing date, close, sentiment, headline_count
   - A control to switch the window: 30 / 90 / 180 / 365 days

6. **EvaluationPanel** — two parts:
   - IC table: full-sample vs out-of-sample, with columns IC, t-stat, p-value,
     n days, hit rate. Mark significance clearly; when `significant` is false,
     say so in words ("not statistically significant").
   - Performance table from `performance[]`: label, total return, Sharpe, vol,
     max drawdown, days. Format returns and drawdowns as percentages with
     sign, Sharpe to 2dp. Colour negative returns red, positive green.
   - Small caption stating parameters were selected on `train_sessions`
     sessions and evaluated once on `test_sessions` held-out sessions.

7. **HeadlineList** — recent headlines for the selected ticker. Each row:
   sentiment label as a coloured pill, score to 2dp, the headline text
   (linked to `url`, opening in a new tab), source and date. Mark rows where
   `is_relevant` is false with a subtle "off-topic" tag — this visibly
   demonstrates the data-quality finding.

8. **MethodologyNote** — a short collapsible section listing the controls:
   one-day lookahead lag, chronological train/test split, 5bps transaction
   costs, cross-sectional ranking, relevance filtering. Keep it factual and
   brief.

### Requirements

- **TypeScript interfaces for every API response.** No `any`.
- **Handle all three states** per data source: loading (skeleton or spinner),
  error (readable message plus a retry button), and empty.
- If the backend is unreachable, show a clear banner: *Backend not running —
  start it with `uvicorn api.main:app --reload`*. Do not let the page render
  blank.
- Dark theme, clean and restrained. This should read as a research tool, not
  a fintech landing page. No gradients, no marketing copy, no fake "live"
  indicators.
- Responsive down to ~768px.
- Number formatting: percentages to 2dp with explicit sign where it's a
  return; p-values to 3dp; IC to 4dp.
- Accessible: real labels on the ticker selector, sufficient contrast, tables
  as actual `<table>` elements.

### Do not

- Do not add authentication, routing, or a state library.
- Do not invent data or hardcode numbers — everything comes from the API.
- Do not imply the strategy is profitable anywhere in the UI.
- Do not modify the Python backend.

## When done

Verify `npm run build` succeeds with no TypeScript errors, then tell me:
the files created, how to run it, and anything in the spec you changed and
why.