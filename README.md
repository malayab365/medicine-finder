# Medicine Search

Look up medicines by name, or describe symptoms and get candidate suggestions, backed by real drug data. See [planning/plan.md](planning/plan.md) for the design and [DEPLOY.md](DEPLOY.md) for deployment.

> Informational only — not medical advice.

## Layout

This is a monorepo with a clear front/back split:

```
backend/    FastAPI JSON API (Python) — RxNorm, OpenFDA, LLM triage, accounts
frontend/   Next.js app (TypeScript, App Router, Tailwind) — all the UI
planning/   design docs
```

The frontend proxies `/api/*` to the backend (Next.js rewrites), so the login
session cookie stays same-origin — no CORS or cross-site cookie juggling in dev.

## Features

- **Name search** (public) — normalizes the query via NIH RxNorm (handles brand/generic and misspellings), then shows the OpenFDA label (uses, dosage, warnings, side effects) plus the most-reported FDA adverse events.
- **Symptom search** *(login required)* — an LLM proposes candidate over-the-counter medicines; their details are re-fetched from OpenFDA so displayed facts come from authoritative data, not the model. A hard-coded emergency check short-circuits before any LLM call, and every response carries a "not medical advice" disclaimer.
- **Accounts** — open self-signup with username + password (hashed with stdlib `scrypt`), stored in a local SQLite file. Symptom search is gated behind a signed-cookie session.
- Per-IP rate limiting (stricter on the symptom endpoint, which calls a paid LLM), in-memory caching.

## Quick start

One command from the repo root starts both services and stops them on Ctrl-C:

```bash
./start.sh
# Frontend: http://localhost:3000  ·  API: http://localhost:8000
```

On first run it sets up the backend `.venv`/`.env`, installs frontend deps, and
seeds `frontend/.env.local`. Set `OPENROUTER_API_KEY` in `backend/.env` to enable
symptom search (name search works without it). Override ports with
`BACKEND_PORT` / `FRONTEND_PORT`.

Prefer separate terminals? Run each side on its own:

```bash
# backend (:8000)
cd backend && ./start.sh

# frontend (:3000)
cd frontend && npm install && cp .env.local.example .env.local && npm run dev
```

## Backend

```bash
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload     # :8000
pytest -q                         # tests
ruff check .                      # lint
```

JSON API: `POST /search/name`, `POST /search/symptom` (login required),
`POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`,
`GET /healthz`. Config loads from `backend/.env` via `pydantic-settings`
(`app/config.py`): `OPENROUTER_API_KEY` for symptom search, `SESSION_SECRET`
(set a long random value in any non-local deploy — it signs the login cookie),
`DATABASE_PATH`, `CORS_ORIGINS`, and the rate-limit knobs. Full table in
[DEPLOY.md](DEPLOY.md).

## Frontend

```bash
cd frontend
npm run dev      # dev server on :3000
npm run build    # production build
npm run lint     # eslint
npm run start    # serve the production build
```

`BACKEND_URL` (in `frontend/.env.local`) points the `/api/*` proxy at the backend.
