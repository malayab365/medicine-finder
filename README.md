# Medicine Search

Web app to look up medicines by name or describe symptoms and get candidate suggestions, backed by real drug data. See [planning/plan.md](planning/plan.md) for the full design and [DEPLOY.md](DEPLOY.md) for deployment.

## Features

- **Name search** — normalizes the query via NIH RxNorm (handles brand/generic and misspellings), then shows the OpenFDA label (uses, dosage, warnings, side effects) plus the most-reported FDA adverse events.
- **Symptom search** *(login required)* — an LLM proposes candidate over-the-counter medicines; their details are re-fetched from OpenFDA so displayed facts come from authoritative data, not the model. A hard-coded emergency check short-circuits before any LLM call, and every response carries a "not medical advice" disclaimer.
- **Accounts** — open self-signup with username + password (hashed with stdlib `scrypt`), stored in a local SQLite file. Symptom search is gated behind a signed-cookie session; name search stays public.
- Per-IP rate limiting (stricter on the symptom endpoint, which calls a paid LLM), in-memory caching, and `robots.txt` blocking indexing.

> Informational only — not medical advice.

## Quick start

```bash
./start.sh
# http://127.0.0.1:8000
```

On first run this creates a `.venv`, installs dependencies, and seeds `.env` from
`.env.example`. Set `OPENROUTER_API_KEY` in `.env` to enable symptom search (name
search works without it). Override the bind address with `HOST` / `PORT`, e.g.
`HOST=0.0.0.0 PORT=9000 ./start.sh`, or pass `--no-reload` for a production-style run.

## Manual setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set OPENROUTER_API_KEY for symptom search
uvicorn app.main:app --reload
```

## Configuration

Settings load from `.env` via `pydantic-settings` (see `app/config.py`).
`OPENROUTER_API_KEY` is required for symptom search, and `SESSION_SECRET` should
be set to a long random string in any non-local deployment (it signs the login
cookie). `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`, `DATABASE_PATH` (SQLite file
for accounts), the API base URLs, and `NAME_RATE_LIMIT_PER_MINUTE` /
`SYMPTOM_RATE_LIMIT_PER_MINUTE` have defaults. Full table in [DEPLOY.md](DEPLOY.md).

## Test

```bash
pytest -q
```

## Lint

```bash
ruff check .
```
