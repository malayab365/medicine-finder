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

---

## Open questions

- Hosting target? (Fly.io / Render / local-only?)
- Do we need rate limiting on the public endpoints? (Probably yes before any public deploy.)
- Are non-US drug databases needed later (e.g., EMA for Europe)?
