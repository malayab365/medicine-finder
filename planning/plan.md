# Medicine Search — Project Plan

## Goal

A web app that lets a user:
1. **Look up a medicine by name** and see uses, dosage, side effects, warnings, and interactions.
2. **Describe symptoms** and get suggested medicines, with prominent safety disclaimers and a recommendation to consult a clinician.

## Non-goals (v1)

- No prescriptions, no purchase flow, no user accounts.
- No claim of medical accuracy — informational only, with disclaimers on every response.
- No support for languages other than English.
- No mobile-native app.

---

## Architecture

```
┌─────────────────┐     HTTP      ┌────────────────────┐
│  Browser (HTML  │ ───────────▶  │  FastAPI backend   │
│  + minimal JS)  │ ◀───────────  │  (Python)          │
└─────────────────┘    JSON       └─────────┬──────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          ▼                 ▼                 ▼
                    ┌──────────┐     ┌──────────┐     ┌──────────┐
                    │ OpenFDA  │     │ RxNorm   │     │ Claude   │
                    │ (labels, │     │ (name    │     │ API      │
                    │ adverse) │     │ normaliz.│     │ (symptom │
                    │          │     │  + RxCUI)│     │  triage) │
                    └──────────┘     └──────────┘     └──────────┘
```

### Why this split

- **RxNorm** normalizes free-text drug names → RxCUI codes, handling brand/generic and misspellings.
- **OpenFDA** drug-label endpoint returns the structured label (indications, dosage, warnings, adverse reactions). Free, no auth.
- **Claude API** handles the symptom → candidate-medicines step, then we re-query OpenFDA for each candidate so the displayed details come from authoritative data rather than the LLM.

Both APIs are free and require no signup, which is why they're the default. Document this choice so it can be swapped later.

---

## Tech stack

- **Backend**: Python 3.11+, FastAPI, `httpx` (async HTTP), `pydantic` (schemas), `anthropic` SDK.
- **Frontend**: server-rendered Jinja2 templates + a single `app.js`. No build step in v1.
- **Caching**: in-memory LRU for OpenFDA/RxNorm responses; upgrade to Redis if traffic grows.
- **Config**: `.env` via `pydantic-settings`. Required vars: `ANTHROPIC_API_KEY`.
- **Tests**: `pytest` + `httpx.AsyncClient` for API tests; record real API responses as fixtures.

---

## Proposed file layout

```
agent-learning/
├── app/
│   ├── main.py              # FastAPI app, routes
│   ├── config.py            # env loading
│   ├── services/
│   │   ├── rxnorm.py        # name → RxCUI, normalization
│   │   ├── openfda.py       # RxCUI/name → label data
│   │   └── triage.py        # symptom text → candidate drug names (Claude)
│   ├── schemas.py           # pydantic request/response models
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html       # search box (name or symptom toggle)
│   │   └── result.html
│   └── static/
│       └── app.js
├── tests/
│   ├── test_rxnorm.py
│   ├── test_openfda.py
│   ├── test_triage.py
│   └── fixtures/            # recorded API responses
├── .claude/agents/          # already scaffolded
├── pyproject.toml
├── .env.example
└── README.md
```

---

## API surface (v1)

| Method | Path                   | Purpose                                      |
|--------|------------------------|----------------------------------------------|
| GET    | `/`                    | Render search page                           |
| POST   | `/search/name`         | `{ "query": "ibuprofen" }` → label JSON      |
| POST   | `/search/symptom`      | `{ "symptoms": "..." }` → candidate list + each one's label data |
| GET    | `/healthz`             | Health check                                 |

Response shape (sketch):

```json
{
  "query": "ibuprofen",
  "matched_name": "Ibuprofen",
  "rxcui": "5640",
  "label": {
    "indications": "...",
    "dosage": "...",
    "warnings": "...",
    "adverse_reactions": "..."
  },
  "disclaimer": "Informational only. Consult a healthcare provider."
}
```

---

## Symptom-search flow

1. User submits free-text symptoms.
2. `triage.py` calls Claude with a constrained prompt:
   - Output a JSON list of up to 5 candidate OTC medicine names (generic preferred).
   - Include severity flag — if symptoms suggest emergency (chest pain, severe bleeding, stroke signs), return `{"emergency": true}` and skip suggestions.
3. For each candidate, call `rxnorm` → `openfda` to pull the real label.
4. Render results with a banner: "Not medical advice. Consult a clinician."

---

## Safety / disclaimers

- Every symptom-search response shows a fixed disclaimer banner.
- Hard-coded emergency keyword check (chest pain, suicide, severe bleeding, stroke signs) as a safety net in front of the LLM call — return the emergency message directly.
- Log every symptom query (anonymized) for later audit; do **not** log PII.
- Add a `robots.txt` blocking indexing while in v1.

---

## Milestones

- **M1 — Skeleton (½ day)**: FastAPI app, `/healthz`, project scaffolding, `.env.example`, basic CI.
- **M2 — Name search (1 day)**: `rxnorm.py` + `openfda.py` + `/search/name` + result template. Includes fixtures and tests.
- **M3 — Symptom search (1 day)**: `triage.py` + Claude integration + emergency guard + `/search/symptom`.
- **M4 — Polish (½ day)**: caching, error states, disclaimer banner, deploy doc.
- **M5 — Stretch**: ~~drug-interaction check between two drugs (RxNav interaction API)~~ (see note), recent adverse-event counts ✅ (done — OpenFDA `/drug/event.json`, shown on the name result), autocomplete on the name field.

  > **Note (2026-06):** NLM **retired the RxNav drug-interaction API in January 2024**, so the interaction-check idea is no longer viable as specified. If we still want interaction checks, we'd need a different source (e.g. a licensed dataset or DDInter) — treat it as a fresh design question, not a quick stretch task.

- **M6 — User accounts + gated symptom search ✅ (done, 2026-06)**: restrict symptom search behind a login so the paid-LLM endpoint is only reachable by registered users. Name search stays public.

  **Requirements**
  - Open self-signup with username + password; password-confirm on register.
  - Symptom search (`POST /search/symptom`) requires a logged-in user → returns `401` when anonymous. Name search unchanged (public).
  - Sessions persist across restarts; accounts survive restarts/redeploys.

  **Design decisions**
  - **Storage:** local **SQLite file** via stdlib `sqlite3` (`app/db.py`), schema created on startup through the FastAPI lifespan. Path from `DATABASE_PATH` (default `medicine_search.db`). Chosen over Postgres to keep the no-infra v1 ethos; over in-memory because accounts must survive restarts.
  - **Sessions:** signed cookie via Starlette `SessionMiddleware` (signed by `SESSION_SECRET`). Only `user_id` is stored in the session; the user is reloaded per request. Natural fit for the server-rendered Jinja2 + form app.
  - **Password hashing:** stdlib `hashlib.scrypt` with a per-user random salt — no extra crypto dependency, consistent with the hand-rolled cache/rate-limiter.
  - **Registration policy:** open self-signup (public `/register`).

  **Surface added**
  - Routes: `GET/POST /register`, `GET/POST /login`, `POST /logout`; templates `register.html`, `login.html`; nav auth state in `base.html`.
  - `app/auth.py` (hashing, register/login, `current_user`/`require_user` deps) + `app/db.py` (SQLite users table).
  - Config: `DATABASE_PATH`, `SESSION_SECRET` (must be overridden in prod). New dep: `itsdangerous` (required by `SessionMiddleware`).
  - Frontend: symptom tab shows a login prompt when logged out; `app.js` handles the `401`.

  **Follow-ups (not in scope yet)**
  - Email verification / password reset (needs email infra).
  - Per-user (not just per-IP) rate limiting now that symptom search is authenticated.
  - Account management (change password, delete account).
  - Move sessions/accounts to a shared store (Redis/Postgres) if scaling beyond a single host.

- **M7 — Split into Next.js frontend + API-only backend ✅ (done, 2026-06)**: separate the UI from the API so the frontend can evolve independently, replacing the server-rendered Jinja2 pages with a Next.js app.

  **Requirements**
  - Monorepo: backend moves to `backend/`, a new Next.js app lives in `frontend/`.
  - Backend becomes a **JSON API** (no server-rendered HTML); all UI is in the frontend.
  - Reuse the existing cookie-session auth (don't rewrite to tokens).
  - Feature parity: name search, gated symptom search, register/login/logout, disclaimers, emergency handling, adverse events.

  **Design decisions**
  - **Frontend stack:** Next.js (App Router) + TypeScript + Tailwind CSS — the modern `create-next-app` defaults.
  - **Frontend ↔ backend:** Next.js **rewrites proxy** `/api/*` → `BACKEND_URL`, so the signed session cookie stays same-origin. Chosen over JWT (no token logic / XSS exposure) and over direct CORS+cross-site cookies (fiddly `SameSite=None`/HTTPS in dev). CORS is still configured (`CORS_ORIGINS`) for the direct-call option.
  - **Backend auth → JSON:** `/auth/register` (201), `/auth/login` (200), `/auth/logout` (204), `/auth/me` (200/401), replacing the form/redirect routes. Hashing, SQLite storage, and `SessionMiddleware` are unchanged from M6.
  - **Removed:** Jinja2 templates + static JS/CSS, and the `jinja2` / `python-multipart` deps.

  **Surface added**
  - `frontend/`: App Router pages (`/`, `/symptoms`, `/login`, `/register`), `lib/api.ts` (typed fetch client), `lib/auth.tsx` (`AuthProvider`/`useAuth`), shared components, `next.config.mjs` proxy, Tailwind. `types.ts` mirrors the backend Pydantic models.
  - `backend/`: CORS middleware, `AuthRequest`/`UserResponse` schemas, `CORS_ORIGINS` config.
  - CI: two jobs — backend (ruff + pytest) and frontend (`npm ci` + lint + build).

  **Follow-ups (not in scope yet)**
  - Containerize the frontend / add a `docker-compose` for one-command local up.
  - Server-side route protection for `/symptoms` (currently gated client-side; the API is the real gate).
  - Shared types generated from the backend OpenAPI schema instead of a hand-kept `types.ts`.

---

## Open questions

- Hosting target? (Fly.io / Render / local-only?)
- Do we need rate limiting on the public endpoints? (Probably yes before any public deploy.)
- Are non-US drug databases needed later (e.g., EMA for Europe)?
