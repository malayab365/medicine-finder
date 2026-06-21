# Backend Code Review — Medicine Finder

**Scope:** `backend/` (FastAPI JSON API, Python)
**Focus:** correctness fixes + a modulith (modular-monolith) restructuring so new features can be added later with minimal churn and better maintainability.
**Date:** 2026-06-20

---

## Implementation status

- **Done:** B1 (thread-safe rate limiter), B3 (logging config), C1 (shared httpx/OpenAI clients), A2 (service layer), C2 (parallel candidate resolution), A1 (feature-module split), **A3 (repository interface/`Protocol`)**.
- **Still open:** B2 (proxy-aware rate-limit key), B4 (evict stale limiter keys), D1–D3 (cookie hardening, login timing, validation dedup), plus the E nits.

The package now follows the feature-module layout below — `core/` (config, logging, clients, middleware), `shared/` (cache, ratelimit), `auth/` (security, repository, service, deps, schemas, router), `medicines/` (providers/, schemas, service, router), `system.py`, and a ~15-line `main.py` composition root. Adding a feature = new package + one `include_router` line.

---

## Overall assessment

The code is genuinely clean: services are isolated, schemas are centralized, config goes through `pydantic-settings`, and the load-bearing safety constraints (emergency keyword check before any LLM call, disclaimer on every symptom response, no PII logging) are respected.

The main weaknesses for *future growth* are:

1. **`main.py` is a god-module** — app wiring, middleware, the rate-limit factory, and every route (health, auth, search) live in one file. Adding a domain means editing it.
2. **Business logic lives inside HTTP handlers** — `search_name`/`search_symptom` orchestrate RxNorm → OpenFDA inline. New functionality = editing route handlers.
3. **The package is organized by *technical layer* (`services/`, `schemas.py`, `db.py`), not by *feature*.** A modulith organizes by feature module, each owning its router + service + schema + storage.

---

## A. Modulith restructuring (the core ask)

Move from layer-oriented to **feature-module** layout. Each module is self-contained and exposes exactly two things to the outside: a `router` and a `service`. Cross-module calls go through the service, never by reaching into another module's internals.

```
app/
  core/                  # framework-level, no business logic
    config.py            # Settings (unchanged)
    logging.py           # NEW: actually configure logging from settings.log_level
    lifespan.py          # startup/shutdown; owns shared httpx clients (see B/C-perf)
    middleware.py        # CORS + SessionMiddleware wiring
    deps.py              # shared FastAPI deps (get_rxnorm_client, etc.)

  shared/                # cross-cutting utilities (no domain knowledge)
    cache.py             # async_lru_cache (unchanged)
    ratelimit.py         # FixedWindowRateLimiter (+ thread-safety, see B1)

  auth/
    router.py            # /auth/* endpoints
    service.py           # register_user / authenticate / validate (today's auth.py)
    security.py          # hash_password / verify_password
    repository.py        # SQLite access (today's db.py) behind a small interface
    schemas.py           # AuthRequest, UserResponse
    deps.py              # require_user / current_user

  medicines/
    router.py            # /search/* endpoints
    service.py           # NEW: orchestration moved OUT of handlers
    schemas.py           # Label, AdverseEvent, *SearchRequest/Response, Candidate
    providers/           # external integrations (today's services/)
      rxnorm.py
      openfda.py
      triage.py

  main.py                # ~15 lines: create app, wire middleware, include routers
```

`main.py` collapses to assembly only:

```python
def create_app() -> FastAPI:
    app = FastAPI(title="Medicine Search API", version="0.3.0", lifespan=lifespan)
    install_middleware(app)
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(medicines.router)
    return app

app = create_app()
```

**Why this helps the stated goal:** adding, say, a "drug interactions" feature becomes a new `app/interactions/` module (router + service + provider) plus one `include_router` line — no edits to auth, search, or `main.py`'s internals. New endpoints in an existing domain are added to that module's router only.

### A2. Extract a service layer (most important single change)

Right now `search_symptom` *is* the business logic. Pull it into `medicines/service.py` so the handler just calls it:

```python
# medicines/service.py
async def search_by_symptom(symptoms: str, clients: Clients) -> SymptomSearchResponse:
    if is_emergency(symptoms):
        return SymptomSearchResponse(emergency=True, message=EMERGENCY_MESSAGE)
    result = await triage(symptoms, client=clients.openai)
    if result.emergency:
        return SymptomSearchResponse(emergency=True, message=EMERGENCY_MESSAGE)
    candidates = await asyncio.gather(*(
        _resolve_candidate(name, clients) for name in result.candidates
    ))
    return SymptomSearchResponse(candidates=candidates)
```

The handler becomes three lines. The orchestration is now unit-testable without HTTP, and reusable (e.g. from a future batch endpoint or CLI).

### A3. Put the repository behind an interface

`db.py` hardcodes `sqlite3`. The CLAUDE.md already says "move to a real DB if traffic grows." Define a small `Protocol` so that swap is a one-module change:

```python
class UserRepository(Protocol):
    def create_user(self, username: str, password_hash: str) -> User: ...
    def get_user_by_username(self, username: str) -> User | None: ...
    def get_user_by_id(self, user_id: int) -> User | None: ...
```

`auth/service.py` depends on the protocol; `SqliteUserRepository` implements it. Postgres later = new implementation, zero changes to the service. (Also: return a typed `User` dataclass instead of leaking `sqlite3.Row` through the auth layer — that `sqlite3.Row` type currently appears in `auth.py`'s public signatures, coupling auth to the storage engine.)

---

## B. Correctness & concurrency (fix regardless of refactor)

**B1 — Rate limiter is not thread-safe.** `rate_limit()` returns a **sync** dependency (`def dependency`), so FastAPI runs it in the threadpool. Multiple threads then mutate `FixedWindowRateLimiter._hits` concurrently with no lock — a classic read-modify-write race that can drop or miscount hits. Add a `threading.Lock` around `check()`:

```python
def check(self, key: str) -> tuple[bool, int]:
    with self._lock:
        ... existing body ...
```
`app/ratelimit.py:18`

**B2 — Rate limiting collapses to *global* behind the proxy.** `request.client.host` (`app/main.py:53`) is the *immediate* peer. Under the Next.js rewrite (and any prod reverse proxy), that's the proxy's IP for every request, so one user's traffic rate-limits everyone. You need to read `X-Forwarded-For` — but only trust it when behind a known proxy, otherwise clients spoof it. Add a `trusted_proxy` flag in config and only then parse the left-most XFF entry.

**B3 — Logging is configured nowhere.** `settings.log_level` (`app/config.py:12`) is defined but never applied. `triage.py`'s `logger.info`/`logger.warning` rely on default root config. Add `core/logging.py` called at startup (`logging.basicConfig(level=settings.log_level)`), otherwise INFO logs may be swallowed and the config knob is dead.

**B4 — `_hits` / cache grow unbounded by key.** The rate limiter never evicts stale keys — every distinct IP stays in the dict forever (slow memory leak over a long-running process). Prune entries whose window has expired during `check`, or periodically.

---

## C. Performance

**C1 — A fresh `httpx.AsyncClient` per call, no connection pooling.** Every `normalize_name` / `fetch_label` / `fetch_adverse_events` that isn't passed a client opens and closes its own client (`app/services/rxnorm.py:45`, `app/services/openfda.py:58/91`). In `search_symptom` with 5 candidates that's ~10+ TCP/TLS handshakes per request. Create long-lived clients in the lifespan and inject them via a dependency (`core/deps.py`). The functions already accept an optional `client` — wire it through instead of defaulting to `None`.

**C2 — Candidate resolution is sequential.** `search_symptom` loops `await` per candidate (`app/main.py:150-157`). With a shared client these are independent — run them with `asyncio.gather` (shown in A2) to cut symptom-search latency roughly N×.

---

## D. Security (lower urgency, worth tracking)

- **D1 — Session cookie hardening.** `SessionMiddleware` (`app/main.py:45`) uses defaults: no `https_only`, no `max_age`. In prod set `https_only=True` (driven by an env flag) so the session cookie isn't sent over HTTP.
- **D2 — User-enumeration via timing.** `authenticate` (`app/auth.py:67`) returns immediately when the username doesn't exist, skipping scrypt; when it exists it runs the (slow) KDF. The timing delta lets an attacker enumerate valid usernames. Run a dummy `verify_password` against a fixed fake hash on the not-found path to equalize timing.
- **D3 — Duplicated validation, two sources of truth.** `AuthRequest` (`app/schemas.py:7-8`) enforces `min_length=1`, but `auth.validate_credentials` enforces the real 3–32 / 8+ limits. Push the real rules into the Pydantic schema (or drop them from the schema) so they can't drift.

---

## E. Minor / nits

- `healthz` doesn't touch the DB — fine, but a real readiness check would verify SQLite is reachable.
- `async_lru_cache` has no TTL; drug labels are stable so it's acceptable, but a stale `None` (transient OpenFDA 404/outage) is cached until evicted. Consider not caching `None`/negative results, or a short TTL.
- `Candidate`/`Label` etc. moving into `medicines/schemas.py` means `openfda.py` imports from its own module instead of the global `app.schemas` — tightens the boundary.

---

## Suggested sequencing

1. **Quick correctness wins** (B1, B3, C1) — small, high value, no restructuring.
2. **Extract service layer** (A2) + parallelize (C2) — biggest maintainability gain.
3. **Feature-module split** (A1) once services exist — mostly file moves + `include_router`.
4. **Repository interface** (A3) when DB swap becomes real.

> The test suite mirrors the current layout (monkeypatches `app.main`, fixtures per service), so a module split needs the import paths in `tests/` updated in lockstep — straightforward but don't skip it.
