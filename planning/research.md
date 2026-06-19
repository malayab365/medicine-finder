# Research notes — Medicine Search

_Sources current as of 2026-06-19. Flag any item that may go stale quickly._

## 1. OpenFDA drug-label API

- **Endpoint**: `GET https://api.fda.gov/drug/label.json?search=<query>&limit=<n>` — single endpoint covers all label lookups, JSON returned. Updated weekly from FDA SPL files; coverage starts June 2009.
- **Querying by name / RxCUI / NDC** — use the structured `openfda.*` subfields, which are the normalized identifiers added by openFDA:
  - Generic name: `search=openfda.generic_name:"ibuprofen"`
  - Brand name: `search=openfda.brand_name:"advil"`
  - RxCUI (preferred when known): `search=openfda.rxcui:"5640"`
  - Product NDC: `search=openfda.product_ndc:"0573-0164"`
- **Key clinical fields** (all returned as arrays of strings — must index `[0]` and HTML-escape):
  - `indications_and_usage`, `dosage_and_administration`, `warnings` (and/or `warnings_and_cautions`), `adverse_reactions`, `contraindications`, `boxed_warning`, `active_ingredient`, `inactive_ingredient`.
- **Rate limits**:
  - No key: 240 req/min and 1,000 req/day per IP.
  - With key (free, signup at api.data.gov): 240 req/min and 120,000 req/day per key.
  - No documented per-second burst limit; expect short-window throttling.
- **Gotchas / recommendations**:
  - One generic drug usually returns **many label documents** (one per manufacturer / SPL submission). Sort by `effective_time` desc and prefer the most recent; consider preferring records where `openfda.product_type` contains `HUMAN OTC DRUG` for the symptom flow.
  - Fields are arrays, not strings, and content is unstructured prose with HTML-ish whitespace. Plan a sanitizer in `openfda.py`.
  - Fields are inconsistently populated — defensively handle `KeyError`/empty arrays for every section.
  - `openfda.rxcui` is **not always present** on every label record; fall back to name-based search.
  - **Recommendation**: Single `fetch_label(rxcui=None, generic_name=None)` helper. Prefer `openfda.rxcui` query first, fall back to `openfda.generic_name`, take the most recent record with the most populated key fields. Get an api.data.gov key even for v1 — it's free and removes the 1k/day cap.
- Sources: [OpenFDA Drug Label overview](https://open.fda.gov/apis/drug/label/), [Searchable fields](https://open.fda.gov/apis/drug/label/searchable-fields/), [OpenFDA authentication & rate limits](https://open.fda.gov/apis/authentication/), [openFDA Drug Label dev guide (RxLabelGuard)](https://rxlabelguard.com/blog/openfda-drug-label-api-developer-guide).

## 2. RxNorm / RxNav

- **Base URL**: `https://rxnav.nlm.nih.gov/REST/`.
- **Fuzzy name → RxCUI**:
  - `/rxcui.json?name=<str>&search=2` — fast, but only returns a hit on exact / normalized matches. Use this first.
  - `/approximateTerm.json?term=<str>&maxEntries=4` — fuzzy fallback for misspellings, extra words, unknown abbreviations (e.g. "Rantidine 15 ML Syrup"). Backed by a real search engine since the Jan-2022 internal rewrite; treat the relative `score` as a ranking signal, not an absolute threshold.
  - **Recommended pattern**: try `/rxcui.json` first; if no rxcui is returned, fall back to `/approximateTerm.json` and pick the top candidate whose `rxaui`/`rxcui` resolves to a term type of `IN` (ingredient), `SCD`, or `SBD`.
- **Brand → generic**: `/rxcui/{rxcui}/related.json?tty=IN+PIN` returns ingredient(s); or `/rxcui/{rxcui}/allrelated.json` for everything. The older `/rxcui/{rxcui}/generic` is also documented.
- **Drug-interaction API (for M5)**: **DISCONTINUED on 2 Jan 2024.** The NLM RxNav drug-drug interaction endpoints (`/interaction/interaction.json`, `/interaction/list.json`) are gone permanently because DrugBank, the upstream source, terminated its free-use license. Do **not** plan around them.
  - Options for M5 interaction check: (a) run **RxNav-in-a-Box** locally (Docker image from NLM, ships with the old interaction data — but the data is now frozen / aging); (b) pay for DrugBank or another commercial DDI API; (c) drop the interaction stretch goal and instead surface OpenFDA `drug_interactions` text from each label (free, but per-drug, not pairwise).
- **Rate limits**: 20 req/sec per IP. NLM explicitly recommends caching responses for 12–24 hours. For higher volume, run RxNav-in-a-Box locally.
- **Recommendation**: Implement the two-step exact-then-fuzzy lookup. For M5, prefer option (c) (per-drug interaction text from OpenFDA labels) — it stays in the free, no-signup stack and avoids the discontinued API. Note RxNav-in-a-Box as a footnote in case interaction quality complaints come in.
- Sources: [RxNorm REST API index](https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html), [getApproximateMatch docs](https://lhncbc.nlm.nih.gov/RxNav/APIs/api-Prescribable.getApproximateMatch.html), [Approximate Matching news (2015 / Jan 2022 update)](https://lhncbc.nlm.nih.gov/RxNav/news/RxNormApproxMatch2015.html), [RxNav Terms of Service (rate limits)](https://lhncbc.nlm.nih.gov/RxNav/TermsofService.html), [NLM Drug Interaction API discontinuation guide](https://www.rxlabelguard.com/blog/nlm-rxnav-drug-interaction-api-discontinued-migration-guide), [DrugBank statement on NIH discontinuation](https://blog.drugbank.com/nih-discontinues-their-drug-interaction-api/).
- **Stale risk**: Low for core endpoints; high for anything DDI-related — re-check before M5.

## 3. Symptom triage with LLM

- **Published guidance (2025)**: Frontiers Medicine 2025 review and the *Drug Safety* "guardrails" paper agree that LLMs **should not be the source of truth** for medication facts — they should pick candidate drugs, then a deterministic system pulls authoritative content. That's already the plan's architecture (Claude proposes names → re-query OpenFDA), which matches best practice.
- **Known failure modes to guard against**:
  - Hallucinated drug names or dosages (mitigated here because real label text comes from OpenFDA, not Claude).
  - Failing to escalate red-flag symptoms (chest pain, suicidality, anaphylaxis).
  - Recommending Rx drugs (warfarin, opioids) when the user expected OTC-only options.
  - Drug interactions with unknown user meds — Claude doesn't know what else the user takes.
- **Constraints to put on the LLM output** (recommended):
  - Force structured JSON with **Anthropic's new structured outputs (beta) using `response_format: {"type": "json_schema", ...}`**. This is cleaner than the old "pretend-tool-use" pattern and gives schema-guaranteed output. (See §7.)
  - Schema requires: `emergency: bool`, `category: "otc"|"rx"|"none"`, `candidates: [{generic_name, why, max_otc, do_not_use_if[]}]` (max 5), `confidence: low|med|high`, plus a verbatim `must_see_clinician_if` string.
  - System prompt: explicitly forbid dosing in mg/kg, Rx-only drugs, and pediatric dosing for under-12s; require generic names only.
- **Is there a free symptom → drug map we could use instead of an LLM?**
  - **MedlinePlus Connect** accepts diagnosis (ICD-10/SNOMED) and medication (RxCUI/NDC) codes and returns patient-education URLs. It is **not** a symptom → drug recommender — it returns reading material, not a drug list. Useful as a "learn more" link from the result page.
  - RxNav `/relatedndc` is just NDC↔NDC navigation, not symptoms.
  - **Conclusion: no free authoritative symptom-to-drug API exists.** Claude (as planned) is the right pick. Wrap it with the OpenFDA re-query and the emergency gate.
- **Recommendation**: Keep the plan as-is. Add structured outputs + a "this is not pharmacist advice" line that Claude must include in every response. Log Claude's full response (with PII stripped) so you can audit failure modes; sample 1–2% for manual review.
- Sources: [Frontiers in Medicine: LLM patient-centered medication guidance (2025)](https://www.frontiersin.org/journals/medicine/articles/10.3389/fmed.2025.1527864/full), [Drug Safety: Guardrails with LLMs in pharmacovigilance (2025, PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12311179/), [Backprompting: Synthetic data for health-advice guardrails (arXiv 2508.18384)](https://arxiv.org/pdf/2508.18384), [MedlinePlus Connect Web Service](https://medlineplus.gov/medlineplus-connect/web-service/).
- **Stale risk**: Medium — LLM safety guidance is evolving fast; revisit before any public launch.

## 4. Emergency-keyword safety net

- **No single maintained public-health "list of dangerous keywords for chatbots" exists.** CDC, AHA, and ASA publish patient-facing symptom lists but not in a form designed for keyword matching.
- **Authoritative source lists to draw from** (combine into one curated list):
  - American Heart Association — heart-attack and stroke warning signs (chest pain/pressure, arm/jaw/back pain, shortness of breath, nausea, cold sweat, lightheadedness).
  - American Stroke Association — **BE FAST**: Balance loss, Eyes (vision loss), Face drooping, Arm weakness, Speech difficulty, Time to call 911.
  - CDC sepsis warning signs (high heart rate, fever + confusion or stiff neck, extreme pain).
  - 988 Suicide & Crisis Lifeline language: "suicide", "kill myself", "end my life", "want to die".
  - Common anaphylaxis signals: "throat closing", "can't breathe", "swelling lips/tongue".
- **Recommended hard-coded list** (curate, then have a clinician review before public launch):
  - chest pain, chest pressure, crushing chest, can't breathe, trouble breathing, shortness of breath at rest, severe bleeding, won't stop bleeding, vomiting blood, blood in stool, coughing up blood
  - stroke, face drooping, slurred speech, sudden weakness, one-sided weakness, sudden vision loss, worst headache of my life
  - suicide, kill myself, want to die, end my life, harm myself, overdose
  - anaphylaxis, throat closing, swelling tongue, swelling lips, can't swallow
  - unconscious, won't wake up, seizure, stiff neck and fever, severe abdominal pain, pregnant and bleeding
- **Action on match**: short-circuit before the LLM call, render: "These symptoms may need emergency care. Call 911 (US) or your local emergency number now. If you are in crisis, call or text 988." Log the match (category, not text) for tuning.
- **Recommendation**: Maintain the list as a YAML file under `app/data/emergency_keywords.yml` grouped by category (cardiac, stroke, mental-health, anaphylaxis, bleeding, other). Match on substring after `.lower().strip()`; no regex on user input is needed for v1. Document that this is a defense-in-depth heuristic, not a triage tool.
- Sources: [AHA: Warning Signs of a Heart Attack](https://www.heart.org/en/health-topics/heart-attack/warning-signs-of-a-heart-attack), [American Stroke Association: Stroke Symptoms (BE FAST)](https://www.stroke.org/en/about-stroke/stroke-symptoms), [AHA: When to call 911](https://www.heart.org/en/health-topics/house-calls/when-to-call-911), [988 Suicide & Crisis Lifeline](https://988lifeline.org/).
- **Stale risk**: Low for the symptom list; the keyword list itself needs human review, not an upstream feed.

## 5. Hosting

| Platform | Free tier (2026) | Cold starts | Secrets UX | Notes |
|---|---|---|---|---|
| **Render** | Yes — Hobby web service, 512 MB RAM, no CC required, app stays deployed indefinitely | Yes (~30s wake from sleep after inactivity) | Built-in env-vars UI; good | Closest thing to truly free hosting; the obvious match for a hobby project |
| **Railway** | No permanent free tier; 30-day trial w/ $5 credit, then ~$5/mo Hobby | None (always-on) | Built-in; very clean | Best DX of the three (push to GitHub → URL) |
| **Fly.io** | No free tier for new users (since 2024); 2-hr trial only | None on paid; scale-to-zero is opt-in | `fly secrets` CLI, solid | Best for multi-region/edge, overkill here |
| **Small VPS (Hetzner CX22 €4.5/mo, DO $4/mo)** | No | None | You manage `.env`/systemd | Cheapest if you don't mind ops; needs reverse proxy, certs, etc. |

- **Recommendation**: **Render free tier** for v1. It matches the "hobby project, informational only, no claim of medical accuracy" framing; the cold-start cost is acceptable; secrets management is trivial. Move to **Railway Hobby ($5/mo)** the moment cold starts annoy real users or the symptom endpoint needs to feel snappy. Avoid Fly.io unless you go multi-region later.
- Sources: [Render: Platforms with a real free tier (2026)](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026), [Railway vs Render vs Fly.io for solo devs (2026)](https://devtoolpicks.com/blog/railway-vs-render-vs-fly-io-solo-developers-2026), [Fly.io Free Tier 2026 analysis](https://www.saaspricepulse.com/blog/flyio-free-tier-2026), [Heroku's dead: Railway vs Render vs Fly.io 2026 (TECHSY)](https://techsy.io/en/blog/railway-vs-render-vs-fly-io).
- **Stale risk**: High — hosting free-tier terms change quarterly. Re-check before any deploy in 2026 H2.

## 6. Disclaimer wording

- **MedlinePlus / NLM standard line** (canonical reputable non-clinical drug-info site):
  > "The information on this site should not be used as a substitute for professional medical care or advice."
- **Suggested verbatim banner string for the app** (combines MedlinePlus phrasing + AHA's "call 911" cue):
  > **This information is not medical advice and is not a substitute for professional care. Always consult a qualified healthcare provider before taking, changing, or stopping any medication. If you think you are having a medical emergency, call 911 or your local emergency number.**
- Show on every page (both flows), not only the symptom-search result. Make the "Call 911" portion visually emphasized when the emergency gate fires.
- Sources: [MedlinePlus: About MedlinePlus / disclaimer language](https://medlineplus.gov/about/general/aboutmedlineplus/), [MedlinePlus Health Literacy](https://medlineplus.gov/healthliteracy.html), [AHA: When to call 911](https://www.heart.org/en/health-topics/house-calls/when-to-call-911).

## 7. Anthropic SDK

- **Current Python SDK**: `anthropic` package, recent 0.4x series (early 2026). Pin a minor version in `pyproject.toml`; the SDK has been moving fast on tool-use and structured-outputs features.
- **Model choice for the triage step**: `claude-haiku-4-5` is the right default — fast, cheap, schema-following ability is excellent for a short JSON output. Upgrade to `claude-sonnet-4-6` only if eval shows Haiku under-suggesting OTC candidates. (The CLI you're running on is Opus 4.7, which would be overkill for this hop.)
- **Structured outputs vs. tool-use for triage**:
  - Prefer the **native structured outputs (`response_format` with a JSON schema)**, released in public beta late 2025. It gives constrained-decoding guarantees and removes the historic "fabricate a fake tool_use block" workaround.
  - Tool-use is the better fit only if you're letting Claude *also* call back into your code (e.g., to look up a candidate's RxCUI mid-response). For v1, you're doing the OpenFDA re-query yourself after Claude returns, so structured output is sufficient and simpler.
- **Prompt caching — applicable here, yes**:
  - The triage system prompt (instructions + emergency-keyword list + JSON schema description) is **fixed across every symptom call**, so it's a textbook caching target.
  - Minimum cacheable size on Haiku 4.5 is **4,096 tokens**; on Sonnet 4.6 it's **1,024 tokens**. If your system prompt is under 4k, either pad it (verbose policy text) or switch to Sonnet for caching to kick in.
  - Read price: 10% of base input. Write price: 1.25× base for 5-min TTL, 2× for 1-hour TTL. For a hobby-traffic app where hits land sporadically, **use `ttl: "1h"`** so the first user of each hour pays the write surcharge once and the rest get the discount.
  - Implementation: place `cache_control: {"type": "ephemeral", "ttl": "1h"}` on the *last* block of the `system` array. Verify by reading `usage.cache_read_input_tokens` and `usage.cache_creation_input_tokens` in every response (log them).
- **Recommendation**: Haiku 4.5 + `response_format` JSON schema + system-prompt caching with 1h TTL. Anthropic SDK ≥ 0.42.
- Sources: [Anthropic Prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Anthropic Structured outputs docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Anthropic Python SDK on PyPI](https://pypi.org/project/anthropic/), [Anthropic engineering: Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use).
- **Stale risk**: Medium — structured outputs is still flagged "beta"; the API shape may change before GA.

## Open questions for the user

- **Hosting target** — confirm Render free tier is acceptable (with cold starts), or budget ~$5/mo for Railway Hobby.
- **API keys** — OK to register a free api.data.gov key for OpenFDA in M2? Removes the 1k/day cap with zero cost.
- **M5 scope correction** — the NLM RxNav drug-interaction API was discontinued in Jan 2024. Pick one: (a) drop the pairwise-interaction stretch goal and surface per-drug `drug_interactions` text from OpenFDA labels instead, (b) self-host RxNav-in-a-Box, or (c) budget for DrugBank's commercial DDI API.
- **Clinician review** — do you want a clinician to sign off on the emergency-keyword list and disclaimer wording before any public deploy?
- **Model choice / cost** — OK to default to Claude Haiku 4.5 with 1-hour prompt caching? Need a max-monthly-$ budget for the Anthropic key.
- **Rate limiting** — confirm we should add (e.g., 30 req/min/IP via `slowapi`) before any public URL is shared.
- **PII / logging policy** — confirm "log symptom text with IPs hashed, retain 30 days" is acceptable for audit, or specify stricter.
- **Geography** — US-only (OpenFDA + RxNorm are US-only data sources) for v1; EMA/Europe is out of scope unless you say otherwise.
