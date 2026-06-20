"""Pull structured drug-label details from OpenFDA — the authoritative source for display."""

import httpx

from app.core.config import settings
from app.medicines.schemas import AdverseEvent, Label
from app.shared.cache import async_lru_cache


def _first(value: list[str] | None) -> str | None:
    """OpenFDA label fields are arrays of strings; we display the first entry."""
    if not value:
        return None
    text = value[0].strip()
    return text or None


def _to_label(result: dict) -> Label:
    return Label(
        indications=_first(result.get("indications_and_usage")),
        dosage=_first(result.get("dosage_and_administration")),
        warnings=_first(result.get("warnings") or result.get("warnings_and_cautions")),
        adverse_reactions=_first(result.get("adverse_reactions")),
    )


async def _search(client: httpx.AsyncClient, search: str) -> Label | None:
    r = await client.get("/drug/label.json", params={"search": search, "limit": 1})
    # OpenFDA returns 404 when a search yields no results.
    if r.status_code == 404:
        return None
    r.raise_for_status()
    results = r.json().get("results") or []
    return _to_label(results[0]) if results else None


@async_lru_cache(maxsize=512)
async def fetch_label(
    *,
    rxcui: str | None = None,
    name: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> Label | None:
    """Fetch a drug label by RxCUI (preferred) then by name. Returns None if nothing matches.

    RxNorm often resolves to an ingredient-level RxCUI that OpenFDA labels don't
    carry, so we fall back to a name search when the RxCUI lookup comes up empty.
    """
    searches = []
    if rxcui:
        searches.append(f'openfda.rxcui:"{rxcui}"')
    if name:
        searches.append(f'openfda.generic_name:"{name}" OR openfda.brand_name:"{name}"')
    if not searches:
        return None

    own_client = client is None
    client = client or httpx.AsyncClient(base_url=settings.openfda_base_url, timeout=10.0)
    try:
        for search in searches:
            label = await _search(client, search)
            if label:
                return label
        return None
    finally:
        if own_client:
            await client.aclose()


@async_lru_cache(maxsize=512)
async def fetch_adverse_events(
    *,
    rxcui: str | None = None,
    name: str | None = None,
    limit: int = 8,
    client: httpx.AsyncClient | None = None,
) -> list[AdverseEvent]:
    """Return the most-reported adverse-event reactions for a drug from OpenFDA.

    These are raw report counts from FAERS, not incidence rates — the UI says so.
    """
    searches = []
    if rxcui:
        searches.append(f'patient.drug.openfda.rxcui:"{rxcui}"')
    if name:
        searches.append(f'patient.drug.openfda.generic_name:"{name}"')
    if not searches:
        return []

    own_client = client is None
    client = client or httpx.AsyncClient(base_url=settings.openfda_base_url, timeout=10.0)
    try:
        for search in searches:
            r = await client.get(
                "/drug/event.json",
                params={"search": search, "count": "patient.reaction.reactionmeddrapt.exact"},
            )
            # OpenFDA returns 404 when a search yields no results.
            if r.status_code == 404:
                continue
            r.raise_for_status()
            results = r.json().get("results") or []
            if results:
                return [
                    AdverseEvent(term=str(item["term"]).title(), count=int(item["count"]))
                    for item in results[:limit]
                ]
        return []
    finally:
        if own_client:
            await client.aclose()
