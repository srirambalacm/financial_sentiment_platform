# RUNBOOK — how to run FinSent

Three sections: **one-time setup**, the **data pipeline** (already done — only
re-run to refresh data), and **running the app** (what you do day to day).

---

## Part 1 — One-time setup

### 1a. Python environment

```powershell
cd C:\Users\bvksr\Downloads\finsent-phase1\finsent
.\finsentvenv\Scripts\Activate.ps1
```

The prompt must read `(finsentvenv)`. If PowerShell blocks the script, run
once: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

> Only ever use `finsentvenv`. If a `.venv` folder still exists, delete it —
> it lacks torch and has caused confusing failures.

```powershell
pip install -r requirements.txt
```

### 1b. Node.js (required for the dashboard)

Download the **LTS** installer from [nodejs.org](https://nodejs.org) and run
it. Accept the defaults. Then **close and reopen VS Code entirely** — it
caches environment variables at launch, so a new terminal alone is not enough.

Verify:

```powershell
node --version
npm --version
```

Then install the frontend packages (once):

```powershell
cd frontend
npm install
cd ..
```

### 1c. API key

`.env` in the project root needs a valid Finnhub key:

```
FINNHUB_API_KEY=yourkeyhere
```

No spaces around `=`. Only needed to *fetch new data* — the app runs fine on
the existing database without it.

---

## Part 2 — Data pipeline

**You have already run all of this.** The database holds 120,375 headlines,
6,647 price bars, and 51,892 sentiment scores. Skip this section unless you
want to refresh the data.

Total runtime is roughly 50 minutes, mostly ingestion and scoring.

```powershell
# Confirm the API key works and history is reachable (~10 seconds)
python -m scripts.check_api

# Prices + news, paginated across 27 windows per ticker (~20 min, 675 requests)
python -m scripts.run_ingest

# Flag headlines that actually mention the tagged company (~1 min)
python -m scripts.tag_relevance

# FinBERT scoring, relevant headlines only (~25 min on CPU)
python -m scripts.score_headlines --relevant-only

# Health check — row counts, sentiment distribution, sample rows
python -m scripts.inspect_db
```

Every stage is resumable. Ingestion deduplicates on a content hash, scoring
only touches unscored rows, and relevance tagging is idempotent — so an
interrupted run can simply be restarted without corruption or double-counting.

### Analysis (fast, re-run any time)

```powershell
# The headline result: IC, coverage, train/test split, out-of-sample backtest
python -m scripts.run_evaluation --relevant-only

# Per-ticker long-only backtest
python -m scripts.run_backtest

# Re-benchmark FinBERT on Financial PhraseBank (~3 min)
python -m scripts.benchmark_model --config sentences_75agree
```

---

## Part 3 — Running the app

This is the day-to-day flow. **Two terminals, both open at once.**

### Terminal 1 — backend

```powershell
.\finsentvenv\Scripts\Activate.ps1
uvicorn api.main:app --reload
```

Leave it running. Serves on `http://127.0.0.1:8000`.
Interactive API docs: `http://127.0.0.1:8000/docs`

### Terminal 2 — frontend

Open a second terminal with the `+` button.

```powershell
cd frontend
npm run dev
```

Leave it running. It prints a URL, usually `http://localhost:5173` — open that
in a browser.

The dashboard talks to the backend through a Vite proxy, so **both must be
running**. If the page shows "Backend not running", Terminal 1 has stopped.

### Stopping

`Ctrl+C` in each terminal.

---

## Quick reference

| Task | Command |
|---|---|
| Activate environment | `.\finsentvenv\Scripts\Activate.ps1` |
| Run tests | `pytest` (expect 84 passed) |
| Start backend | `uvicorn api.main:app --reload` |
| Start frontend | `cd frontend` then `npm run dev` |
| Database health check | `python -m scripts.inspect_db` |
| Re-run the analysis | `python -m scripts.run_evaluation --relevant-only` |
| Build deployment DB | `python -m scripts.build_deploy_db` |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `No module named 'torch'` | Wrong virtual environment. `deactivate`, then activate `finsentvenv`. |
| `npm is not recognized` | Node.js not installed, or VS Code not restarted after installing it. |
| `claude is not recognized` | Restart VS Code — it caches PATH at launch. |
| Dashboard shows "Backend not running" | Terminal 1 stopped. Restart uvicorn. |
| Ingest returns `401 Unauthorized` | Key in `.env` is stale. Copy the current one from finnhub.io. |
| `pytest` shows fewer than 84 tests | A test file is missing from `tests/`. |
| First `/api/evaluation` call is slow | Expected — ~3.5s cold, ~2ms cached for the next hour. |