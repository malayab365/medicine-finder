# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Web app for searching medicines by name or symptom. See `planning/plan.md` for the design (and `planning/research.md` for background), `README.md` for setup, and `DEPLOY.md` for deployment. Milestones M1–M4 are complete and M5 is partly done: name search (`/search/name`), symptom search (`/search/symptom`), the three services, in-memory caching, per-IP rate limiting, `robots.txt`, and (from M5) OpenFDA adverse-event counts on the name result. Still open: name-field autocomplete (M5). The M5 drug-interaction check is **not viable** — NLM retired the RxNav interaction API in Jan 2024 (see `planning/plan.md`).

## Commands

```bash
pip install -e ".[dev]"         # install with dev deps
uvicorn app.main:app --reload   # run dev server on :8000
pytest -q                       # run tests
pytest tests/test_healthz.py::test_healthz_returns_ok   # single test
ruff check .                    # lint
```

## Architecture

FastAPI backend + Jinja2-rendered HTML frontend. Three external dependencies, each isolated in `app/services/`:

- `rxnorm.py` — normalizes free-text drug names to RxCUI codes (NIH RxNorm, free, no auth); falls back to fuzzy `approximateTerm` matching for misspellings.
- `openfda.py` — pulls structured drug labels (indications, dosage, warnings) and adverse-event counts (`/drug/event.json`) from OpenFDA. **Authoritative source for displayed details.** Note: RxNorm often yields an *ingredient-level* RxCUI that OpenFDA records don't carry, so both `fetch_label` and `fetch_adverse_events` try the RxCUI first, then fall back to a generic-name search.
- `triage.py` — symptom text → candidate drug names via an LLM (OpenRouter, OpenAI-compatible API). Output is *only* candidate names; details are then re-fetched from OpenFDA. This keeps the LLM out of the factual-claims path.

When adding a search feature, follow that pattern: LLM for fuzzy input handling, real APIs for any data shown to the user.

Endpoints: `POST /search/name` (`{query}` → label JSON + `adverse_events`) and `POST /search/symptom` (`{symptoms}` → candidate list + each candidate's OpenFDA label). Both are rate-limited per client IP (`app/ratelimit.py`; symptom is stricter since it calls the paid LLM). **Symptom search additionally requires a logged-in user** (`Depends(auth.require_user)` → 401 if anonymous); name search stays public.

Auth (`app/auth.py` + `app/db.py`): open self-signup with username/password, passwords hashed with stdlib `hashlib.scrypt` (no extra crypto dep), users stored in a local SQLite file (stdlib `sqlite3`, path from `DATABASE_PATH`, schema created on startup via the FastAPI lifespan). Sessions are signed cookies via Starlette `SessionMiddleware` (`SESSION_SECRET` signs them — override in prod); only `user_id` is stashed in the session and the user is reloaded per request. Form-rendered pages: `GET/POST /register`, `GET/POST /login`, `POST /logout`. The frontend hides the symptom form when logged out and shows a login prompt; `app.js` also handles a `401` from the endpoint. Service results are cached with a small async-aware LRU (`app/cache.py` — `functools.lru_cache` can't wrap coroutines). Also served: `GET /healthz`, `GET /robots.txt` (blocks indexing in v1). Config and external base URLs live in `app/config.py` (`pydantic-settings`, loaded from `.env`); `OPENROUTER_API_KEY` is the only required secret, and `SESSION_SECRET` should be overridden in any non-local deploy (`OPENROUTER_MODEL`/`OPENROUTER_BASE_URL` are configurable, defaults `openrouter/auto` and `https://openrouter.ai/api/v1`; `DATABASE_PATH` defaults to `medicine_search.db`; rate limits via `NAME_RATE_LIMIT_PER_MINUTE`/`SYMPTOM_RATE_LIMIT_PER_MINUTE`).

Tests use `pytest-asyncio` in `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed). Service tests inject an `httpx.AsyncClient` backed by `MockTransport` with recorded fixtures under `tests/fixtures/` rather than hitting live APIs; endpoint tests monkeypatch the service functions on `app.main`. An autouse fixture in `tests/conftest.py` clears the service caches, rate-limit counters, and the users table between tests — keep it, or cached results, 429s, and accounts will leak across tests. A session-scoped fixture points `DATABASE_PATH` at a throwaway SQLite file; the `register_and_login(client)` helper there logs a TestClient in for symptom-endpoint tests. CI (`.github/workflows/ci.yml`) runs `ruff check .` then `pytest -q` on push to `main` and on PRs; ruff lint set is `E,F,I,W,UP,B` at line-length 100.

## Safety constraints (load-bearing)

- Symptom search must show a disclaimer banner on every response.
- A hard-coded emergency keyword check runs **before** any LLM call (chest pain, suicide, severe bleeding, stroke signs) and short-circuits with an emergency message.
- Never log raw symptom text with PII.

## Subagents

Project-scoped subagents live in `.claude/agents/`. See `.claude/agents/README.md` for the file format.
