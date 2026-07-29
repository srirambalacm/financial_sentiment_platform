# FinSent frontend

A read-only research dashboard reporting Phase 3's finding: financial news
sentiment showed **no** predictive power over next-day returns for the
tracked tickers (out-of-sample IC ≈ -0.006, p ≈ 0.79). This is not a trading
tool.

## Stack

Vite + React + TypeScript, Tailwind CSS, Recharts, plain `fetch`. No router,
no state library — it's a single page.

## Running it

1. Start the backend from the repo root (a separate terminal):

   ```
   uvicorn api.main:app --reload
   ```

   It serves `http://127.0.0.1:8000`; docs at `/docs`.

2. In this directory, install and run the dev server:

   ```
   cd frontend
   npm install
   npm run dev
   ```

   Vite proxies `/api/*` to the backend (see `vite.config.ts`), so open the
   URL Vite prints (typically `http://localhost:5173`).

3. Production build check:

   ```
   npm run build
   ```

If the backend isn't running, the page still renders and shows a banner
telling you to start it, plus per-section retry buttons.
