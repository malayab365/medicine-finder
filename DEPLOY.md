# Deployment

The app is a stateless FastAPI service (no database, in-memory cache only), so it
runs anywhere that can run a Python ASGI app or a container. Hosting target is still
an open question (see `planning/plan.md`); the Docker path below works on Fly.io,
Render, Railway, Cloud Run, or a plain VM.

## Configuration

Set these as environment variables (or a `.env` file — see `.env.example`):

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `OPENROUTER_API_KEY` | **yes** | — | Secret; needed for symptom search. Set via the host's secrets manager, never commit it. |
| `OPENROUTER_MODEL` | no | `openrouter/auto` | Pin a specific model for deterministic suggestions. |
| `OPENROUTER_BASE_URL` | no | `https://openrouter.ai/api/v1` | |
| `OPENFDA_BASE_URL` | no | `https://api.fda.gov` | |
| `RXNORM_BASE_URL` | no | `https://rxnav.nlm.nih.gov/REST` | |
| `LOG_LEVEL` | no | `INFO` | |

## Run locally (production-style)

```bash
pip install .
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For multiple workers behind a process manager:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

> Note: the LRU cache is per-process, so each worker keeps its own cache. That's
> fine at v1 scale; move to Redis (per `plan.md`) if you need a shared cache.

## Container

```bash
docker build -t medicine-search .
docker run -p 8000:8000 -e OPENROUTER_API_KEY=sk-... medicine-search
```

The image binds to `$PORT` when the platform sets it, else 8000.

## Fly.io (example)

```bash
fly launch --no-deploy            # generates fly.toml; set internal_port = 8000
fly secrets set OPENROUTER_API_KEY=sk-...
fly deploy
```

## Render (example)

- New **Web Service** → from this repo (Docker runtime, the Dockerfile is detected).
- Add `OPENROUTER_API_KEY` as an environment variable.
- Health check path: `/healthz`.

## Notes

- `GET /robots.txt` returns `Disallow: /` to block indexing while in v1.
- `GET /healthz` returns `{"status": "ok"}` for platform health checks.
- Rate limiting is **not** built in yet (open question in `plan.md`) — add it
  (e.g. a reverse-proxy limit or `slowapi`) before any public deploy, since the
  symptom endpoint calls a paid LLM.
