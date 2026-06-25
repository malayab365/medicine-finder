# Persistent Symptom-Search Cache — Research & Proposed Change

**Requirement:** Store the query and search results for **symptom search** in persistent
storage. On a repeat of the *same* query, return the stored results **without making the
LLM call**.

**Date:** 2026-06-20
**Related:** [`plan.md`](plan.md), [`symptom-search-without-llm.md`](symptom-search-without-llm.md),
`../review.md` (E-nit on caching `None`), `backend/app/medicines/service.py`,
`backend/app/auth/repository.py` (the A3 repository pattern this mirrors)

---

## 1. Current state (what the research found)

### The symptom-search flow today
`POST /search/symptom` → `medicines/router.py` (auth gate + rate limit) →
`service.search_by_symptom(symptoms, clients)`:

1. `is_emergency(symptoms)` — hard-coded keyword check, **before any LLM call**. Returns an
   emergency response and short-circuits.
2. `triage(symptoms)` — **the LLM call** (OpenRouter, paid, non-deterministic). Returns
   candidate drug *names* only.
3. For each candidate, `_resolve_candidate` → RxNorm `normalize_name` + OpenFDA `fetch_label`
   (run concurrently with `asyncio.gather`).
4. Assemble `SymptomSearchResponse` (candidates + disclaimer).

### What is and isn't cached today
- **In-memory only, per provider:** `normalize_name`, `fetch_label`, `fetch_adverse_events`
  are wrapped with `async_lru_cache` (`app/shared/cache.py`, `maxsize=512`). These caches are
  **process-local and lost on restart**.
- **The LLM `triage` step has NO cache at all.** Every symptom search — even an identical one
  in the same process — hits the LLM. This is the single most expensive, slowest, and only
  *paid* step. **It is exactly the gap this requirement targets.**
- There is **no persistent cache anywhere**. The only persistent storage is the SQLite users
  table (`app/auth/repository.py`).

### Architectural facts that shape the design
- **Modulith / feature-module layout.** Each feature package owns its router + service +
  schema + *storage*. A persistent symptom cache belongs in `app/medicines/`, not in `auth/`
  or a shared layer.
- **The A3 repository pattern is the template.** `auth/repository.py` already establishes:
  a `Protocol` interface + a typed dataclass + a `SqliteXxxRepository` impl + a module-level
  singleton + `init_db()`/`reset_xxx()` lifecycle helpers wired into `main.py`'s lifespan and
  `tests/conftest.py`. We copy this shape exactly.
- **SQLite is already the persistent store** (`settings.database_path`, stdlib `sqlite3`, one
  connection per op). Reuse the same DB file — no new dependency, consistent with the
  hand-rolled cache/limiter philosophy.
- **Safety constraint — PII.** CLAUDE.md: *"Never log raw symptom text with PII."* Symptom
  text is free-form and may contain personal/health information. **Persisting raw symptom
  text to disk has the same exposure as logging it** and should be avoided. This drives the
  key design below (store a *hash*, not the raw text).
- **Tests** point `database_path` at a throwaway SQLite file (session fixture) and an autouse
  fixture resets per-test state (`reset_users()`, cache clears, limiter resets). Any new
  persistent cache must be reset there too, or results leak across tests.

---

## 2. Design decisions

### 2a. What exactly do we cache? (recommended: the **LLM output**, not the full response)

| | **Option A — cache triage candidates (recommended)** | Option B — cache full `SymptomSearchResponse` |
|---|---|---|
| Stored | LLM candidate name list (`["ibuprofen", ...]`) | Entire JSON response incl. OpenFDA labels |
| Skips LLM? | ✅ yes (the requirement) | ✅ yes |
| OpenFDA freshness | ✅ labels re-fetched live on each hit | ❌ serves possibly-stale labels |
| Respects "LLM out of the factual path" | ✅ exactly | ⚠️ freezes facts at first search |
| Latency on a hit | fast (skips LLM; OpenFDA re-fetch, itself in-mem cached) | fastest (one DB read) |
| Stored-row size | tiny (a few names) | larger (full label text) |

**Recommendation: Option A.** It directly satisfies "no LLM call," keeps the displayed drug
facts authoritative and fresh (re-fetched from OpenFDA, which has its own in-memory cache),
and stores the least data. The design keeps the door open to Option B later (store the full
response JSON in the same row) if profiling shows OpenFDA re-fetch is the bottleneck.

### 2b. Cache key — hash the *normalized* query (and store no raw text)

- **Normalize** before hashing so trivially-different inputs hit the same entry:
  `" ".join(symptoms.lower().split())` (lowercase, trim, collapse internal whitespace).
  Optionally strip surrounding punctuation. Keep it deterministic and simple — this is exact
  match after normalization, **not** semantic match (semantic similarity is out of scope;
  would need embeddings — see Future work).
- **Key = `sha256(normalized).hexdigest()`**, used as the table primary key.
- **Store the hash, not the raw symptom text.** This satisfies the PII constraint: a one-way
  hash can't be reversed to the symptoms, and we don't need the raw text — the cache only has
  to recognize a repeat, not display "you searched X." (If product later needs search
  history, that's a separate, consent-gated feature.)

### 2c. Where the code lives — new module storage mirroring A3

```
app/medicines/
  repository.py   # NEW — SymptomCacheRepository Protocol + SqliteSymptomCacheRepository
  service.py      # MODIFIED — check cache, skip triage on hit, store on miss
  ...
```

---

## 3. Proposed implementation

### 3a. `app/medicines/repository.py` (new)

```python
"""Persistent cache for symptom-search results, behind a small repository interface.

Mirrors the auth repository (A3): the service depends only on the
`SymptomCacheRepository` Protocol and a typed dataclass, never on sqlite3. Only a
SHA-256 hash of the normalized symptom text is stored — never the raw text — so the
cache holds no PII (see CLAUDE.md safety constraints).
"""

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


def cache_key(symptoms: str) -> str:
    normalized = " ".join(symptoms.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CachedTriage:
    candidates: list[str]   # LLM candidate names (Option A)
    created_at: float       # epoch seconds


class SymptomCacheRepository(Protocol):
    def get(self, key: str) -> CachedTriage | None: ...
    def put(self, key: str, candidates: list[str]) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS symptom_cache (
    key         TEXT PRIMARY KEY,        -- sha256 of normalized symptoms
    candidates  TEXT NOT NULL,           -- JSON list of LLM candidate names
    created_at  REAL NOT NULL            -- epoch seconds, for TTL
);
"""


class SqliteSymptomCacheRepository:
    def __init__(self, ttl_seconds: int | None = None) -> None:
        self._ttl = ttl_seconds  # None = never expire

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(settings.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def get(self, key: str) -> CachedTriage | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT candidates, created_at FROM symptom_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        if self._ttl is not None and time.time() - row["created_at"] > self._ttl:
            return None  # stale; treat as miss (optionally delete here)
        return CachedTriage(candidates=json.loads(row["candidates"]), created_at=row["created_at"])

    def put(self, key: str, candidates: list[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO symptom_cache (key, candidates, created_at) "
                "VALUES (?, ?, ?)",
                (key, json.dumps(candidates), time.time()),
            )

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM symptom_cache")


_sqlite = SqliteSymptomCacheRepository(ttl_seconds=settings.symptom_cache_ttl_seconds or None)
symptom_cache: SymptomCacheRepository = _sqlite


def init_db() -> None:
    _sqlite.init_db()


def reset_symptom_cache() -> None:
    _sqlite.reset()
```

### 3b. `app/medicines/service.py` (modified `search_by_symptom`)

```python
from app.medicines.repository import cache_key, symptom_cache

async def search_by_symptom(symptoms: str, clients: Clients) -> SymptomSearchResponse:
    # 1. Emergency check ALWAYS runs first — never cached, never skipped.
    if is_emergency(symptoms):
        return SymptomSearchResponse(emergency=True, message=EMERGENCY_MESSAGE)

    # 2. Persistent cache lookup — a hit skips the LLM entirely.
    key = cache_key(symptoms)
    cached = symptom_cache.get(key) if settings.symptom_cache_enabled else None
    if cached is not None:
        candidate_names = cached.candidates
    else:
        result = await triage(symptoms)            # the LLM call
        if result.emergency:
            return SymptomSearchResponse(emergency=True, message=EMERGENCY_MESSAGE)
        candidate_names = result.candidates
        # 3. Store only on a successful, non-empty, non-emergency triage.
        if settings.symptom_cache_enabled and candidate_names:
            symptom_cache.put(key, candidate_names)

    # 4. Always re-resolve labels live from OpenFDA (fresh, authoritative).
    candidates = await asyncio.gather(
        *(_resolve_candidate(name, clients) for name in candidate_names)
    )
    return SymptomSearchResponse(candidates=list(candidates))
```

`symptom_cache` is imported as a module-level name, consistent with how providers are
referenced for monkeypatching.

### 3c. Wiring & config

- **`app/main.py` lifespan:** add `medicines_repository.init_db()` next to
  `repository.init_db()` (both target the same SQLite file).
- **`app/core/config.py`:** add
  - `symptom_cache_enabled: bool = True`
  - `symptom_cache_ttl_seconds: int = 0`  (`0` = never expire; e.g. `2592000` for 30 days)
- **`tests/conftest.py`:** call `medicines_repository.init_db()` in the session DB fixture and
  `medicines_repository.reset_symptom_cache()` in the autouse `_clear_service_state` fixture,
  so cached rows don't leak across tests (same reason `reset_users()` is there).

---

## 4. Edge cases & decisions

- **Emergency text is never cached.** The hard-coded check runs before the cache, and a triage
  result with `emergency=True` is not stored — the keyword net must always fire, and emergencies
  are cheap to recompute.
- **Empty candidate list not cached.** Avoids pinning a transient bad/empty LLM result (mirrors
  the review's E-nit about caching `None`). A later query gets a fresh attempt.
- **Staleness / TTL.** Triage output is fairly stable, but model/prompt changes can improve it.
  TTL (`symptom_cache_ttl_seconds`) bounds how long a stale answer survives. `0` = never expire
  for the simplest start. A prompt/model change can be force-invalidated by bumping a version
  column or `DELETE FROM symptom_cache` on deploy (see Future work).
- **Cache stampede.** Two identical concurrent first-time queries can both miss and both call the
  LLM before either writes. Acceptable at v1 scale (idempotent, `INSERT OR REPLACE`). A
  per-key async lock would close it if needed.
- **Unbounded growth.** Each distinct normalized query is one small row. At v1 scale this is
  fine; if needed, prune by `created_at` (a periodic `DELETE WHERE created_at < ?`) — note this
  is the same unbounded-key concern flagged for the rate limiter (review B4).
- **Normalization is exact-match only.** "headache" and "head ache" or "I have a headache" are
  *different* keys. That's intentional for v1 correctness/simplicity. Semantic matching is
  future work.

---

## 5. Testing

- **Cache hit skips the LLM:** monkeypatch `app.medicines.service.triage` with a counter (or
  one that raises). First symptom search calls it once and populates the cache; an identical
  second search returns the same candidates **without** calling `triage`. This is the core
  acceptance test for the requirement.
- **Normalization:** `"  Headache "` and `"headache"` resolve to the same cached entry.
- **Emergency not cached:** an emergency query doesn't write a row; the keyword check still
  fires on a repeat.
- **TTL:** with a short TTL, an aged row is treated as a miss and re-triages.
- **No PII at rest:** assert the `symptom_cache` table stores only the hash + candidate names,
  never the raw symptom text.
- Existing endpoint tests still pass because `reset_symptom_cache()` runs between tests.

---

## 6. Files to change (summary)

| File | Change |
|---|---|
| `app/medicines/repository.py` | **New** — Protocol + `SqliteSymptomCacheRepository` + `cache_key` + singleton + `init_db`/`reset` |
| `app/medicines/service.py` | Check cache → skip `triage` on hit; store candidate names on miss |
| `app/core/config.py` | Add `symptom_cache_enabled`, `symptom_cache_ttl_seconds` |
| `app/main.py` | `medicines_repository.init_db()` in lifespan |
| `tests/conftest.py` | init + per-test reset of the symptom cache table |
| `tests/test_*` | New tests (cache hit skips LLM, normalization, emergency-not-cached, TTL) |
| `CLAUDE.md` | Document the persistent symptom cache + the "hash, never raw text" rule |

No frontend or API-contract changes: the response shape is unchanged; this is a transparent
backend cache.

---

## 7. Future work / out of scope

- **Semantic matching** (embeddings + vector similarity) so paraphrases share a cache entry —
  far larger scope and a new dependency; deliberately excluded here.
- **Option B (cache the full response)** if OpenFDA re-fetch becomes the latency bottleneck —
  add a nullable `response_json` column to the same row.
- **Shared/Redis cache** if the app scales to multiple backend processes (the SQLite file is
  fine for a single process; an in-memory cache would not be shared across workers).
- **Cache versioning / invalidation on prompt or model change** (a `prompt_version` column, or
  wipe-on-deploy) so improved triage isn't masked by stale entries.
- **Cache metrics** (hit/miss counters, exposed via a health/admin endpoint) to measure LLM
  cost savings.
```
