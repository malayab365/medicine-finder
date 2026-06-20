"""Search orchestration — the use-case layer between HTTP handlers and providers.

The route handlers in `medicines/router.py` stay thin: they validate input,
enforce auth / rate limits, and delegate here. This module wires the providers
(RxNorm → OpenFDA, plus the LLM triage step) into the two search flows, so the
business logic is testable without HTTP and reusable from other entry points.

Provider functions are referenced as module-level names on purpose — tests
monkeypatch them here (e.g. `app.medicines.service.triage`) to stub external calls.
"""

import asyncio

from app.core.clients import Clients
from app.medicines.providers.openfda import fetch_adverse_events, fetch_label
from app.medicines.providers.rxnorm import normalize_name
from app.medicines.providers.triage import is_emergency, triage
from app.medicines.schemas import (
    EMERGENCY_MESSAGE,
    Candidate,
    NameSearchResponse,
    SymptomSearchResponse,
)


async def search_by_name(query: str, clients: Clients) -> NameSearchResponse:
    match = await normalize_name(query, client=clients.rxnorm)
    rxcui = match.rxcui if match else None
    matched_name = match.name if match else None
    label = await fetch_label(rxcui=rxcui, name=matched_name or query, client=clients.openfda)
    adverse_events = await fetch_adverse_events(
        rxcui=rxcui, name=matched_name or query, client=clients.openfda
    )
    return NameSearchResponse(
        query=query,
        matched_name=matched_name,
        rxcui=rxcui,
        label=label,
        adverse_events=adverse_events,
    )


async def _resolve_candidate(name: str, clients: Clients) -> Candidate:
    match = await normalize_name(name, client=clients.rxnorm)
    rxcui = match.rxcui if match else None
    matched_name = match.name if match else None
    label = await fetch_label(rxcui=rxcui, name=matched_name or name, client=clients.openfda)
    return Candidate(name=name, matched_name=matched_name, rxcui=rxcui, label=label)


async def search_by_symptom(symptoms: str, clients: Clients) -> SymptomSearchResponse:
    # Hard-coded emergency check runs before any LLM call.
    if is_emergency(symptoms):
        return SymptomSearchResponse(emergency=True, message=EMERGENCY_MESSAGE)

    # triage builds its own OpenAI/OpenRouter client lazily (see core.clients).
    result = await triage(symptoms)
    if result.emergency:
        return SymptomSearchResponse(emergency=True, message=EMERGENCY_MESSAGE)

    # Candidates are independent — resolve them concurrently.
    candidates = await asyncio.gather(
        *(_resolve_candidate(name, clients) for name in result.candidates)
    )
    return SymptomSearchResponse(candidates=list(candidates))
