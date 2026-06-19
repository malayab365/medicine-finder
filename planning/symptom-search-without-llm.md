# Symptom Search Without an LLM — Options & Trade-offs

**Question:** Does symptom search *have* to use an LLM? Are there free APIs for the same job?
**Date:** 2026-06-19
**Related:** [`spec.md`](spec.md) §6.3, [`plan.md`](plan.md), `app/services/triage.py`

> ⚠️ API availability changes over time (NLM retired the RxNav *interaction* API in Jan 2024). The notes below reflect knowledge as of early 2026 and should be verified with a live query before committing to an approach.

---

## Short answer

**No, an LLM is not required.** The LLM in `triage.py` does exactly one thing: turn messy free-text symptoms into candidate drug *names*. That's a fuzzy-NLP problem. It can be replaced with deterministic lookups against free APIs.

The trade-off is **input quality, not correctness** — the displayed facts already come from OpenFDA regardless of how candidates are generated.

---

## Free / no-auth options

### 1. OpenFDA indications search (already integrated)

OpenFDA's label endpoint is full-text searchable on `indications_and_usage`, so symptom keywords map to drugs with **zero new dependencies**:

```
GET /drug/label.json?search=indications_and_usage:"headache"&limit=5
```

- **Pros:** already integrated; free; no auth; stays in the authoritative-source paradigm; no LLM cost.
- **Cons:** crude — matches label *text* literally. Colloquial phrasing ("runny nose") matches poorly, and results are noisy (any label mentioning the word). Best with symptoms normalized to a small controlled vocabulary first.

### 2. RxClass `MAY_TREAT` relationship (NIH, free, no auth)

RxClass (same family as RxNorm; **separate** from the retired interaction API) exposes a `may_treat` relationship from MED-RT, mapping a **condition** → drugs that treat it.

- **Pros:** authoritative; structured; explicit "this drug may treat this condition."
- **Cons:** keys off a *condition concept*, not raw symptoms. Still need symptom-text → condition — the part the LLM was solving.

### 3. Symptom-checker APIs (ApiMedic/Priaid, Infermedica, EndlessMedical)

These map symptoms → likely *conditions* (not drugs). Mostly **freemium**, not truly free — ApiMedic/Priaid historically had a limited free tier; Infermedica is commercial. Would chain symptom→condition, then RxClass for condition→drug.

---

## The honest catch

The LLM's real value is the **fuzzy natural-language step** — handling vague, multi-symptom, colloquial input (e.g. "stuffy nose and can't stop sneezing"). None of the free structured APIs replicate that well; they need cleaner, more structured input. A no-LLM build is very doable but will feel more rigid and keyword-driven.

---

## Recommended hybrid (no LLM)

Keep the existing safety model, drop the LLM:

1. Hard-coded **emergency keyword check** (unchanged — already works this way).
2. Small **symptom-keyword → condition/indication map** (controlled vocabulary).
3. **OpenFDA indications search** *or* **RxClass `may_treat`** → candidate drug names.
4. Re-fetch real labels from OpenFDA (unchanged).

This preserves "LLM/heuristics for fuzzy input, real APIs for displayed facts."

---

## Comparison

| Option | Free | No auth | Handles fuzzy text | New dependency | Maps to |
|--------|------|---------|--------------------|----------------|---------|
| LLM (current) | paid | key | ✅ excellent | already in | drug names |
| OpenFDA indications | ✅ | ✅ | ❌ keyword-only | none (already in) | drugs |
| RxClass `may_treat` | ✅ | ✅ | ❌ needs condition | new client | condition → drugs |
| Symptom-checker API | freemium | key | ⚠️ structured input | new client | symptoms → conditions |

---

## Open / to verify

- Confirm RxClass `may_treat` endpoint shape and current availability with a live query.
- Confirm OpenFDA `indications_and_usage` search quality on real symptom phrases.
- Decide whether a keyword→condition vocabulary is worth maintaining vs. keeping the LLM.
</content>
