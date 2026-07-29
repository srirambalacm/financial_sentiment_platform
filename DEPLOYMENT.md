# Deployment guide — Phase 5

Backend to Render, frontend to Vercel, CI on GitHub Actions. Both hosts have
free tiers sufficient for a portfolio demo.

---

## 0. CI (do this first — it is the quick win)

Already configured in `.github/workflows/ci.yml`. On every push to `main` it
runs the backend test suite on Python 3.11 and 3.12, and type-checks and
builds the frontend.

CI installs `requirements-ci.txt` rather than `requirements.txt`, which omits
torch, transformers, scikit-learn and yfinance. The test suite genuinely does
not need them — `src/sentiment.py` imports torch lazily inside the model
loader, so the module imports fine without it. This takes the install from
several minutes and ~2GB down to a few seconds.

Once pushed, add the status badge to the top of `README.md`:

```markdown
![CI](https://github.com/<your-username>/<your-repo>/actions/workflows/ci.yml/badge.svg)
```

A green badge on a public repo is disproportionately persuasive for the effort.

---

## 1. Prepare the database

The working database is ~54MB, above GitHub's 50MB file warning. Build the
compacted serving copy:

```bash
python -m scripts.build_deploy_db
```

This drops the two ingestion-only columns (`dedup_hash`, `fetched_at`) and
their index, then VACUUMs — roughly 32% smaller, with row counts verified
identical so every figure in the README still matches what the live API
reports.

Then allow it past `.gitignore`, which currently excludes all of `data/`:

```gitignore
data/
!data/finsent-deploy.db
```

```bash
git add -f data/finsent-deploy.db
```

A ~37MB file in git is not elegant. It is, however, the pragmatic choice for a
read-only demo over a static corpus: the alternative is provisioning a hosted
Postgres and writing a migration, which adds real operational surface for no
benefit a reviewer will notice. Say exactly that if asked — recognising when
*not* to reach for infrastructure is a legitimate engineering judgement.

---

## 2. Backend → Render

1. Push to GitHub.
2. On [render.com](https://render.com): **New → Web Service**, connect the repo.
3. Configure:

   | Field | Value |
   |---|---|
   | Environment | Python 3 |
   | Build command | `pip install -r requirements-ci.txt` |
   | Start command | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |

   Use `requirements-ci.txt` here too. The API never runs the model — scoring
   is a batch job in `scripts/` — so torch on the server would be 2GB of
   deployment weight that is never imported.

4. Add environment variables:

   | Key | Value |
   |---|---|
   | `FINSENT_DB_PATH` | `data/finsent-deploy.db` |
   | `FINSENT_CORS_ORIGINS` | your Vercel URL, once you have it |

5. Deploy, then check `https://<your-service>.onrender.com/health`.

**Free tier caveat:** Render spins services down after inactivity, so the first
request after an idle period takes ~30s. Note this in your README so a reviewer
does not mistake a cold start for a broken deployment.

---

## 3. Frontend → Vercel

The frontend currently reaches the backend through a Vite dev proxy, which
does not exist in a production build. Make the base URL configurable first —
give Claude Code this instruction:

> In `frontend/src/api/client.ts`, replace the hardcoded `/api` base with
> `const API_BASE = import.meta.env.VITE_API_URL ?? ""` and prefix every fetch
> path with it. Keep the Vite dev proxy working when the variable is unset, so
> local development is unchanged. Add `frontend/.env.example` documenting
> `VITE_API_URL`.

Then:

1. On [vercel.com](https://vercel.com): **Add New → Project**, import the repo.
2. Set **Root Directory** to `frontend`.
3. Framework preset: Vite. Build command `npm run build`, output `dist`.
4. Add environment variable `VITE_API_URL` = your Render URL (no trailing
   slash).
5. Deploy.

Finally, go back to Render and set `FINSENT_CORS_ORIGINS` to your Vercel
domain, then redeploy. Leaving CORS open to `*` in production is sloppy and an
interviewer may well ask about it.

---

## 4. Finish the README

- [ ] CI badge at the top
- [ ] Live demo link, with a one-line note about the cold-start delay
- [ ] Screenshot of the dashboard (the verdict banner and chart together)
- [ ] Screenshot of `/docs` showing the endpoint list
- [ ] Tick Phases 4 and 5 in the roadmap

The dashboard screenshot matters most. It is the first thing a recruiter looks
at, and it shows a real interface rendering a real, honestly-reported result.

---

## Verification checklist

- [ ] `pytest` passes locally (84 tests)
- [ ] CI green on GitHub
- [ ] `data/finsent-deploy.db` committed; `.env` still untracked (`git status`)
- [ ] `/health` returns `{"status":"ok"}` on Render
- [ ] `/api/evaluation` returns real numbers on Render (slow first call, fast after)
- [ ] Vercel dashboard loads live data with no CORS errors in the browser console
- [ ] `FINSENT_CORS_ORIGINS` restricted to the Vercel domain