# Medicine Search — Technical Specification

**Status:** v0.1.0 (M1–M4 complete, M5 partly done)
**Audience:** engineers working on or integrating with this service
**Related docs:** [`plan.md`](plan.md) (design rationale), [`research.md`](research.md) (background), [`../README.md`](../README.md) (setup), [`../DEPLOY.md`](../DEPLOY.md) (deployment)

This document describes *what the system does and how it is built today*, derived from the implementation. Where the original plan and the code diverge (e.g. LLM provider), this spec reflects the code.

---

## 1. Overview

A single-page web app for looking up medicines two ways:

1. **By name** — free-text drug name → normalized identity + structured label (uses, dosage, warnings, adverse reactions) + most-reported adverse-event counts.
2. **By symptom** — free-text symptom description → up to 5 candidate OTC medicines, each with its real OpenFDA label, fronted by emergency safety checks and a disclaimer.

The design principle throughout: **the LLM only handles fuzzy input (symptom → candidate names); every fact shown to the user comes from an authoritative API (RxNorm, OpenFDA).** The model is never in the factual-claims path.

---

## 2. Architecture

```
┌─────────────────┐     HTTP/JSON   ┌────────────────────┐
│  Browser        │ ──────────────▶ │  FastAPI backend   │
│  (Jinja2 HTML   │ ◀────────────── │  (app/main.py)     │
│   + app.js)     │                 └─────────┬──────────┘
└─────────────────┘                           │
                      ┌───────────────────────┼───────────────────────┐
                      ▼                        ▼                       ▼
                ┌──────────┐            ┌──────────┐            ┌──────────────┐
                │ RxNorm   │            │ OpenFDA  │            │ OpenRouter   │
                │ (NIH,    │            │ (FDA,    │            │ (OpenAI-     │
                │  free)   │            │  free)   │            │  compatible) │
                └──────────┘            └──────────┘            └──────────────┘
              name → RxCUI         labels + adverse events     symptom → names
```

- **Backend:** FastAPI, async throughout (`httpx.AsyncClient`).
- **Frontend:** server-rendered Jinja2 templates (`base.html`, `index.html`) + a single `app.js`, `style.css`. No build step.
- **External services** are each isolated behind a module in `app/services/`.

### Module map

| File | Responsibility |
|------|----------------|
| `app/main.py` | FastAPI app, routes, rate-limit wiring |
| `app/config.py` | `pydantic-settings` config from `.env` |
| `app/schemas.py` | Pydantic request/response models + disclaimer/emergency constants |
| `app/cache.py` | Async-aware in-process LRU decorator |
| `app/ratelimit.py` | In-process fixed-window per-IP rate limiter |
| `app/services/rxnorm.py` | Name → RxCUI normalization (exact + fuzzy) |
| `app/services/openfda.py` | Label + adverse-event fetch |
| `app/services/triage.py` | Symptom → candidate names (LLM) + emergency keyword check |
| `app/templates/`, `app/static/` | Frontend |

---

## 3. Tech stack

- **Language/runtime:** Python ≥ 3.11
- **Web:** `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`
- **Models/validation:** `pydantic` ≥ 2.9, `pydantic-settings`
- **HTTP client:** `httpx` (async)
- **LLM client:** `openai` SDK pointed at OpenRouter's OpenAI-compatible endpoint
- **Dev:** `pytest`, `pytest-asyncio`, `ruff`

> **Note on the LLM provider:** `plan.md` describes the Anthropic SDK; the implementation uses the **OpenRouter** OpenAI-compatible API via the `openai` SDK (`app/services/triage.py`). This spec follows the code.

---

## 4. Configuration

All config is loaded by `Settings` (`app/config.py`) from environment / `.env`. Unknown keys are ignored (`extra="ignore"`).

| Setting | Env var | Default | Notes |
|---------|---------|---------|-------|
| `openrouter_api_key` | `OPENROUTER_API_KEY` | `""` | **Only required secret** (symptom search) |
| `openrouter_model` | `OPENROUTER_MODEL` | `openrouter/auto` | |
| `openrouter_base_url` | `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | |
| `openfda_base_url` | `OPENFDA_BASE_URL` | `https://api.fda.gov` | |
| `rxnorm_base_url` | `RXNORM_BASE_URL` | `https://rxnav.nlm.nih.gov/REST` | |
| `log_level` | `LOG_LEVEL` | `INFO` | |
| `name_rate_limit_per_minute` | `NAME_RATE_LIMIT_PER_MINUTE` | `60` | per client IP |
| `symptom_rate_limit_per_minute` | `SYMPTOM_RATE_LIMIT_PER_MINUTE` | `15` | stricter; guards paid LLM |

OpenFDA and RxNorm require no auth. Name search works without an API key; only symptom search needs `OPENROUTER_API_KEY`.

---

## 5. API surface

| Method | Path | Auth | Rate limit | Purpose |
|--------|------|------|-----------|---------|
| `GET` | `/` | none | none | Render search page |
| `GET` | `/healthz` | none | none | Health check → `{"status": "ok"}` |
| `GET` | `/robots.txt` | none | none | `Disallow: /` (blocks indexing in v1) |
| `GET`/`POST` | `/register` | none | none | Self-signup (form) |
| `GET`/`POST` | `/login` | none | none | Login (form) |
| `POST` | `/logout` | none | none | Clear session |
| `POST` | `/search/name` | none | name limiter | Name lookup |
| `POST` | `/search/symptom` | **login** | symptom limiter | Symptom triage (401 if anonymous) |
| static | `/static/*` | none | none | `app.js`, `style.css` |

### 5.0 Authentication

Symptom search is gated behind a user account; name search is public. Accounts are
open self-signup (username + password). Passwords are hashed with stdlib
`hashlib.scrypt` (per-user random salt) in `app/auth.py`; users are stored in a
local SQLite file (`app/db.py`, stdlib `sqlite3`, path `DATABASE_PATH`, schema
created on startup via the FastAPI lifespan). Sessions are **signed cookies** via
Starlette `SessionMiddleware` (signed by `SESSION_SECRET`); only `user_id` is held
in the session and the user is reloaded per request. `Depends(auth.require_user)`
on `/search/symptom` returns **401** when anonymous; the frontend hides the symptom
form when logged out and `app.js` handles the 401 with a login prompt.

### 5.1 `POST /search/name`

**Request** (`NameSearchRequest`):
```json
{ "query": "ibuprofen" }
```
`query`: 1–200 chars, required.

**Response** (`NameSearchResponse`):
```json
{
  "query": "ibuprofen",
  "matched_name": "Ibuprofen",
  "rxcui": "5640",
  "label": {
    "indications": "…",
    "dosage": "…",
    "warnings": "…",
    "adverse_reactions": "…"
  },
  "adverse_events": [
    { "term": "Nausea", "count": 1234 }
  ],
  "disclaimer": "Informational only. Not medical advice. Consult a healthcare provider."
}
```
`matched_name`, `rxcui`, and `label` are `null` when nothing resolves. `adverse_events` is `[]` when none are found. Each field of `label` is independently nullable.

**Flow** (`search_name`):
1. `normalize_name(query)` → RxNorm match (RxCUI + canonical name) or `None`.
2. `fetch_label(rxcui, name)` → OpenFDA label (RxCUI first, name fallback).
3. `fetch_adverse_events(rxcui, name)` → top reaction counts.
4. Assemble response.

### 5.2 `POST /search/symptom`

**Request** (`SymptomSearchRequest`):
```json
{ "symptoms": "runny nose and sore throat" }
```
`symptoms`: 1–1000 chars, required.

**Response** (`SymptomSearchResponse`):
```json
{
  "emergency": false,
  "message": null,
  "candidates": [
    { "name": "acetaminophen", "matched_name": "Acetaminophen", "rxcui": "161", "label": { "…": "…" } }
  ],
  "disclaimer": "Informational only. Not medical advice. Consult a healthcare provider."
}
```

**Emergency response:**
```json
{
  "emergency": true,
  "message": "Your symptoms may indicate a medical emergency. Call your local emergency number (such as 911) or go to the nearest emergency room now.",
  "candidates": [],
  "disclaimer": "…"
}
```

**Flow** (`search_symptom`):
1. **`is_emergency(symptoms)`** — hard-coded keyword check, runs **before any LLM call**. On hit → emergency response, short-circuit.
2. `triage(symptoms)` — LLM returns `{emergency, candidates[]}`. If `emergency` → emergency response.
3. For each candidate name: `normalize_name` → `fetch_label` (no adverse-event lookup here). Note the candidate `name` is the LLM's proposed name; `matched_name`/`rxcui`/`label` come from the real APIs.
4. Return candidate list.

### Error responses

- `422` — request validation failure (Pydantic), e.g. empty or over-length input.
- `429` — rate limit exceeded; body `{"detail": "Too many requests. Please slow down."}` plus a `Retry-After` header (seconds).
- Upstream HTTP errors propagate from `httpx.raise_for_status()`; OpenFDA `404` (no results) is handled gracefully as "no data" rather than an error.

---

## 6. External service integration

### 6.1 RxNorm (`app/services/rxnorm.py`)

Resolves free text → `RxNormMatch(rxcui, name)`:
1. `/rxcui.json?name=` — exact match.
2. Fallback `/approximateTerm.json?term=&maxEntries=1` — fuzzy match for misspellings/partials.
3. `/rxcui/{rxcui}/property.json?propName=RxNorm Name` — canonical name.

Returns `None` if no RxCUI resolves. 10s timeout. Cached (see §7).

### 6.2 OpenFDA (`app/services/openfda.py`)

**Authoritative source for displayed details.**

`fetch_label(rxcui, name)` queries `/drug/label.json`:
- Tries `openfda.rxcui:"{rxcui}"` first, then `openfda.generic_name:"{name}" OR openfda.brand_name:"{name}"`.
- The fallback exists because RxNorm often yields an *ingredient-level* RxCUI that OpenFDA label records don't carry.
- Maps array-valued label fields (first entry) into `Label{indications, dosage, warnings, adverse_reactions}`. `warnings` falls back to `warnings_and_cautions`.

`fetch_adverse_events(rxcui, name, limit=8)` queries `/drug/event.json` with `count=patient.reaction.reactionmeddrapt.exact`:
- Tries `patient.drug.openfda.rxcui` then `patient.drug.openfda.generic_name`.
- Returns up to `limit` `AdverseEvent{term, count}`, term title-cased.
- **These are raw FAERS report counts, not incidence rates** — the UI must say so.

Both handle OpenFDA `404` as "no results." 10s timeout. Cached.

### 6.3 OpenRouter LLM (`app/services/triage.py`)

`triage(symptoms)` calls the chat-completions API with:
- `temperature=0`, `response_format={"type": "json_object"}`.
- A constrained system prompt: return only `{"emergency": bool, "candidates": [≤5 names]}`, prefer generics, no dosages/explanations.
- Robust parse: malformed JSON → empty `TriageResult` (logged as a warning, no crash).
- **Logging:** only counts (`emergency=…, candidates=N`) — **never raw symptom text** (PII constraint).

---

## 7. Caching (`app/cache.py`)

`functools.lru_cache` can't wrap coroutines (it would cache the coroutine, awaitable once), so `async_lru_cache` is a custom decorator that awaits the call and caches the **result** in an `OrderedDict` (LRU eviction, `maxsize` default 256; services use 512).

- Cache key = `(args, sorted kwargs)` **excluding `client`** (the injected HTTP client is irrelevant to the result).
- Applied to `normalize_name`, `fetch_label`, `fetch_adverse_events`.
- Exposes `cache_clear()` and `cache_info()`.
- In-process only; upgrade to Redis if scaling beyond a single worker matters.

---

## 8. Rate limiting (`app/ratelimit.py`)

`FixedWindowRateLimiter(limit, window=60s)` — in-process, per-key (client IP) fixed window.

- `check(key)` records a hit, returns `(allowed, retry_after_seconds)`.
- Two instances in `main.py`: `name_limiter` and (stricter) `symptom_limiter`, wired as FastAPI dependencies.
- Client key = `request.client.host` (or `"unknown"`).
- **Per-process:** behind N workers each enforces its own window. Adequate for v1; move to a shared store (Redis) for global limits.

---

## 9. Safety constraints (load-bearing)

These are requirements, not nice-to-haves:

1. **Disclaimer on every response.** `DISCLAIMER` is a default field on both response models, so it's always present. Symptom-search UI must render a visible disclaimer banner.
2. **Emergency keyword check before any LLM call.** `is_emergency()` runs first in `search_symptom`; on match it short-circuits to `EMERGENCY_MESSAGE`. Keywords cover chest pain, suicidal ideation, severe bleeding, and stroke signs (drooping, slurred speech, one-sided numbness), plus breathing difficulty. The LLM has its own emergency path as a second layer.
3. **No PII in logs.** Raw symptom text is never logged — only aggregate counts.
4. **LLM out of the factual path.** The model proposes candidate *names* only; all displayed facts are re-fetched from OpenFDA.
5. **No indexing in v1.** `robots.txt` returns `Disallow: /`.

---

## 10. Testing

- `pytest` with `pytest-asyncio` in `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed).
- **Service tests** inject an `httpx.AsyncClient` backed by `MockTransport` with recorded fixtures in `tests/fixtures/` — no live API calls.
- **Endpoint tests** monkeypatch the service functions on `app.main`.
- An **autouse fixture** (`tests/conftest.py`) clears service caches and rate-limit counters between tests — required, or cached results and 429s leak across tests.
- Coverage: `test_healthz`, `test_rxnorm`, `test_openfda`, `test_triage`, `test_search_name`, `test_search_symptom`, `test_cache`, `test_ratelimit`.

### CI (`.github/workflows/ci.yml`)

On push to `main` and on PRs: `ruff check .` → `pytest -q`. Ruff lint set `E,F,I,W,UP,B`, line length 100, target `py311`.

### Commands

```bash
pip install -e ".[dev]"         # install with dev deps
uvicorn app.main:app --reload   # dev server on :8000
pytest -q                       # run tests
ruff check .                    # lint
```

---

## 11. Data models (`app/schemas.py`)

| Model | Fields |
|-------|--------|
| `NameSearchRequest` | `query: str` (1–200) |
| `Label` | `indications`, `dosage`, `warnings`, `adverse_reactions` — all `str \| None` |
| `AdverseEvent` | `term: str`, `count: int` |
| `NameSearchResponse` | `query`, `matched_name?`, `rxcui?`, `label?`, `adverse_events[]`, `disclaimer` |
| `SymptomSearchRequest` | `symptoms: str` (1–1000) |
| `Candidate` | `name`, `matched_name?`, `rxcui?`, `label?` |
| `SymptomSearchResponse` | `emergency`, `message?`, `candidates[]`, `disclaimer` |

Constants: `DISCLAIMER`, `EMERGENCY_MESSAGE`.

---

## 12. Known limitations & open items

- **Drug-interaction check (M5) is not viable as originally specified** — NLM retired the RxNav interaction API in January 2024. A new source (e.g. licensed dataset, DDInter) would be a fresh design task. See `plan.md`.
- **Autocomplete on the name field (M5)** — still open.
- **Adverse-event counts are raw FAERS report counts**, not incidence rates; not statistically adjusted.
- **Cache and rate limiter are per-process** — not shared across workers/replicas.
- **English only; US drug data only** (OpenFDA/RxNorm). No EMA/international sources.
- **No accounts, prescriptions, or purchase flow** — informational only by design.
</content>
</invoke>
