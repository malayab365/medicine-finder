# Deployment

Two services deploy independently:

- **`backend/`** — FastAPI JSON API with an in-memory cache and a small **SQLite
  file for user accounts** (symptom search is gated behind login). Give it a
  writable/persistent path for the SQLite file (`DATABASE_PATH`) so accounts
  survive restarts and redeploys.
- **`frontend/`** — Next.js app. It proxies `/api/*` to the backend via Next.js
  rewrites; set `BACKEND_URL` to the backend's URL. Because the proxy keeps API
  calls same-origin, the session cookie works without CORS.

Hosting target is still an open question (see `planning/plan.md`); the Docker path
below works on Fly.io, Render, Railway, Cloud Run, or a plain VM. Run both behind
HTTPS in production — the session cookie carries the login.

## Backend configuration

Set these as environment variables (or `backend/.env` — see `backend/.env.example`):

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `OPENROUTER_API_KEY` | **yes** | — | Secret; needed for symptom search. Set via the host's secrets manager, never commit it. |
| `SESSION_SECRET` | **prod** | `dev-insecure-change-me` | Signs the login session cookie. Set a long random value (`python -c "import secrets; print(secrets.token_hex(32))"`); keep it stable, or all sessions are invalidated. |
| `DATABASE_PATH` | no | `medicine_search.db` | SQLite file for user accounts. Point at a persistent volume in production. |
| `OPENROUTER_MODEL` | no | `openrouter/auto` | Pin a specific model for deterministic suggestions. |
| `CORS_ORIGINS` | no | `http://localhost:3000` | Comma-separated origins allowed to call the API with credentials. Set to the frontend's deployed origin (only needed if the frontend calls the API directly instead of via the proxy). |
| `OPENROUTER_BASE_URL` | no | `https://openrouter.ai/api/v1` | |
| `OPENFDA_BASE_URL` | no | `https://api.fda.gov` | |
| `RXNORM_BASE_URL` | no | `https://rxnav.nlm.nih.gov/REST` | |
| `LOG_LEVEL` | no | `INFO` | |

## Frontend configuration

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `BACKEND_URL` | no | `http://localhost:8000` | Where Next.js proxies `/api/*`. Set to the backend's deployed URL. |

## Run locally (production-style)

Backend:

```bash
cd backend
pip install .
uvicorn app.main:app --host 0.0.0.0 --port 8000          # or --workers 4
```

Frontend:

```bash
cd frontend
npm ci
npm run build
BACKEND_URL=http://localhost:8000 npm run start          # :3000
```

> Note: the LRU cache and rate-limit counters are per-process, so each worker
> keeps its own. That's fine at v1 scale; move to Redis (per `plan.md`) if you need
> them shared. The SQLite accounts DB *is* shared (one file), but SQLite handles
> only modest write concurrency — fine here, since writes happen only on
> register/login. Set the same `SESSION_SECRET` across all workers/replicas, or
> cookies signed by one won't validate on another.

## Container (backend)

The backend Dockerfile lives in `backend/`. Build with that as the context:

```bash
docker build -t medicine-search-api backend
docker run -p 8000:8000 -e OPENROUTER_API_KEY=sk-... -e SESSION_SECRET=... medicine-search-api
```

The image binds to `$PORT` when the platform sets it, else 8000. The frontend
deploys as a standard Next.js app (e.g. Vercel, or `npm run build && npm run start`
in a Node container) with `BACKEND_URL` pointed at the API.

## Fly.io (example, backend)

```bash
cd backend
fly launch --no-deploy            # generates fly.toml; set internal_port = 8000
fly secrets set OPENROUTER_API_KEY=sk-... SESSION_SECRET=$(python -c "import secrets;print(secrets.token_hex(32))")
fly deploy
```

## Render (example)

- Backend: New **Web Service** → root `backend` (Docker runtime). Add
  `OPENROUTER_API_KEY` and `SESSION_SECRET`. Health check path: `/healthz`.
- Frontend: New **Web Service** (Node) → root `frontend`, build `npm ci && npm run build`,
  start `npm run start`. Set `BACKEND_URL` to the backend service URL.

## Notes

- `GET /healthz` returns `{"status": "ok"}` for platform health checks.
- Per-IP rate limiting is built in (`app/ratelimit.py`), stricter on the symptom
  endpoint since it calls a paid LLM. It's per-process and in-memory; front it with
  a reverse-proxy/Redis limit if you run many workers and need a global cap.
- Serve over HTTPS in production — the session cookie carries the login.
