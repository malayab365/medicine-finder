# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

App for searching medicines by name or symptom. See `planning/plan.md` for the design (and `planning/research.md` for background), `README.md` for setup, and `DEPLOY.md` for deployment. Milestones M1–M4 complete; M5 done (recent adverse-event counts + name-field autocomplete); M6 (accounts/gated symptom search) and M7 (front/back split) done. The M5 drug-interaction check is **not viable** — NLM retired the RxNav interaction API in Jan 2024 (see `planning/plan.md`).

**Monorepo layout (M7):** `backend/` is a FastAPI **JSON API** (no server-rendered HTML anymore); `frontend/` is a **Next.js app** (TypeScript, App Router, Tailwind) that owns all UI. The frontend proxies `/api/*` to the backend via Next.js rewrites (`frontend/next.config.mjs`), keeping the session cookie same-origin. Paths below are relative to `backend/` unless noted.

## Commands

Backend (run from `backend/`):

```bash
pip install -e ".[dev]"         # install with dev deps
uvicorn app.main:app --reload   # run API on :8000
pytest -q                       # run tests
pytest tests/test_healthz.py::test_healthz_returns_ok   # single test
ruff check .                    # lint
```

Frontend (run from `frontend/`):

```bash
npm install
npm run dev      # :3000, proxies /api/* → BACKEND_URL (.env.local)
npm run build    # production build (also typechecks + lints)
npm run lint
```

## Architecture

FastAPI JSON API backend (`backend/`) + Next.js frontend (`frontend/`).

**Backend module layout (modulith):** the app is organized by feature package, not by technical layer. `app/main.py` is a ~15-line composition root that wires middleware and `include_router`s the feature routers. Packages:
- `app/core/` — framework-level, no business logic: `config.py` (settings), `logging.py` (`configure_logging`), `clients.py` (shared pooled `httpx` clients for RxNorm/OpenFDA in a `Clients` container, created in the lifespan and injected via `get_clients`; the triage provider builds its own OpenAI client lazily), `middleware.py` (`install_middleware`: CORS + sessions).
- `app/shared/` — cross-cutting utilities: `cache.py` (async LRU), `ratelimit.py` (`FixedWindowRateLimiter` + the `rate_limit` dependency factory).
- `app/auth/` — `security.py` (scrypt hashing), `repository.py` (SQLite), `service.py` (register/authenticate/validate), `deps.py` (`current_user`/`require_user`), `schemas.py`, `router.py`.
- `app/medicines/` — `providers/` (the three external integrations below), `schemas.py`, `service.py` (search orchestration — name + symptom, candidates resolved concurrently with `asyncio.gather`), `router.py` (owns the two rate limiters).
- `app/system.py` — `/healthz`, `/robots.txt`.

Adding a feature = a new package exposing an `APIRouter` + one `include_router` line in `main.py`.

The three external dependencies are each isolated in `app/medicines/providers/`:

- `rxnorm.py` — normalizes free-text drug names to RxCUI codes (NIH RxNorm, free, no auth); falls back to fuzzy `approximateTerm` matching for misspellings.
- `openfda.py` — pulls structured drug labels (indications, dosage, warnings) and adverse-event counts (`/drug/event.json`) from OpenFDA. **Authoritative source for displayed details.** Note: RxNorm often yields an *ingredient-level* RxCUI that OpenFDA records don't carry, so both `fetch_label` and `fetch_adverse_events` try the RxCUI first, then fall back to a generic-name search.
- `triage.py` — symptom text → candidate drug names via an LLM (OpenRouter, OpenAI-compatible API). Output is *only* candidate names; details are then re-fetched from OpenFDA. This keeps the LLM out of the factual-claims path.

When adding a search feature, follow that pattern: LLM for fuzzy input handling, real APIs for any data shown to the user.

Endpoints: `POST /search/name` (`{query}` → label JSON + `adverse_events`), `POST /search/symptom` (`{symptoms}` → candidate list + each candidate's OpenFDA label), and `GET /search/suggest` (`?q=` → `{suggestions: [...]}`, public, powers name-field autocomplete), all in `app/medicines/router.py` and delegating to `app/medicines/service.py`. All three are rate-limited per client IP (`app/shared/ratelimit.py`; symptom is stricter since it calls the paid LLM, suggest is generous since it's served from cache). **Symptom search additionally requires a logged-in user** (`Depends(auth.deps.require_user)` → 401 if anonymous); name search and suggest stay public. Suggestions come from RxNorm's `displaynames` list (`rxnorm.suggest_names`), fetched once and cached in-process (`_load_display_names`), then prefix-filtered locally per keystroke (prefix matches first, then substring; shorter names first) rather than calling RxNorm per request.

Auth (`app/auth/`), **JSON API** (M7): open self-signup with username/password, passwords hashed with stdlib `hashlib.scrypt` (no extra crypto dep), users stored in a local SQLite file (stdlib `sqlite3`, path from `DATABASE_PATH`, schema created on startup via the FastAPI lifespan). Sessions are signed cookies via Starlette `SessionMiddleware` (`SESSION_SECRET` signs them — override in prod); only `user_id` is stashed in the session and the user is reloaded per request. Endpoints return JSON: `POST /auth/register` (201), `POST /auth/login` (200), `POST /auth/logout` (204), `GET /auth/me` (200 or 401). CORS is enabled for `CORS_ORIGINS` with credentials (not needed under the dev proxy, but supports direct cross-origin calls). The frontend's `lib/auth.tsx` (`AuthProvider`/`useAuth`) calls `/auth/me` to track session state; `/symptoms` shows a login prompt when logged out. Service results are cached with a small async-aware LRU (`app/shared/cache.py` — `functools.lru_cache` can't wrap coroutines). Also served: `GET /healthz`, `GET /robots.txt` (`app/system.py`). Config lives in `app/core/config.py` (`pydantic-settings`, loaded from `backend/.env`); `OPENROUTER_API_KEY` is the only required secret, `SESSION_SECRET` should be overridden in any non-local deploy (`OPENROUTER_MODEL`/`OPENROUTER_BASE_URL` default `openrouter/auto` and `https://openrouter.ai/api/v1`; `DATABASE_PATH` defaults to `medicine_search.db`; `CORS_ORIGINS` defaults to `http://localhost:3000`; rate limits via `NAME_RATE_LIMIT_PER_MINUTE`/`SYMPTOM_RATE_LIMIT_PER_MINUTE`/`SUGGEST_RATE_LIMIT_PER_MINUTE`).

Frontend (`frontend/`): Next.js App Router. `app/page.tsx` = name search (public), `app/symptoms/page.tsx` = symptom search (gated client-side via `useAuth`), `app/login` + `app/register` use the shared `components/AuthForm.tsx`. `lib/api.ts` is the typed fetch client (all calls go to `/api/*` with `credentials: "include"`); `types.ts` mirrors the backend Pydantic models. Keep them in sync when changing response shapes.

Tests use `pytest-asyncio` in `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed). Service tests inject an `httpx.AsyncClient` backed by `MockTransport` with recorded fixtures under `tests/fixtures/` rather than hitting live APIs; endpoint tests monkeypatch the provider functions on `app.medicines.service` (the orchestration call site) and authenticate via the `register_and_login(client)` helper (`POST /auth/register`). An autouse fixture in `tests/conftest.py` clears the service caches, rate-limit counters, and the users table between tests — keep it, or cached results, 429s, and accounts will leak across tests. A session-scoped fixture points `DATABASE_PATH` at a throwaway SQLite file. CI (`.github/workflows/ci.yml`) has two jobs: **backend** (`ruff check .` + `pytest -q` in `backend/`) and **frontend** (`npm ci` + `npm run lint` + `npm run build` in `frontend/`); ruff lint set is `E,F,I,W,UP,B` at line-length 100.

## Safety constraints (load-bearing)

- Symptom search must show a disclaimer banner on every response.
- A hard-coded emergency keyword check runs **before** any LLM call (chest pain, suicide, severe bleeding, stroke signs) and short-circuits with an emergency message.
- Never log raw symptom text with PII.

## Subagents

Project-scoped subagents live in `.claude/agents/`. See `.claude/agents/README.md` for the file format.
