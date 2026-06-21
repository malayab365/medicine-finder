"""Normalize free-text drug names to RxCUI codes via NIH RxNorm (free, no auth)."""

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.shared.cache import async_lru_cache


@dataclass
class RxNormMatch:
    rxcui: str
    name: str


async def _exact_rxcui(query: str, client: httpx.AsyncClient) -> str | None:
    r = await client.get("/rxcui.json", params={"name": query})
    r.raise_for_status()
    ids = r.json().get("idGroup", {}).get("rxnormId") or []
    return ids[0] if ids else None


async def _approx_rxcui(query: str, client: httpx.AsyncClient) -> str | None:
    """Fall back to fuzzy matching for misspellings/partial names."""
    r = await client.get("/approximateTerm.json", params={"term": query, "maxEntries": 1})
    r.raise_for_status()
    candidates = r.json().get("approximateGroup", {}).get("candidate") or []
    return candidates[0].get("rxcui") if candidates else None


async def _name_for_rxcui(rxcui: str, client: httpx.AsyncClient) -> str | None:
    r = await client.get(f"/rxcui/{rxcui}/property.json", params={"propName": "RxNorm Name"})
    r.raise_for_status()
    props = r.json().get("propConceptGroup", {}).get("propConcept") or []
    return props[0].get("propValue") if props else None


@async_lru_cache(maxsize=512)
async def normalize_name(
    query: str, *, client: httpx.AsyncClient | None = None
) -> RxNormMatch | None:
    """Resolve a free-text name to its RxCUI and canonical RxNorm name, or None."""
    own_client = client is None
    client = client or httpx.AsyncClient(base_url=settings.rxnorm_base_url, timeout=10.0)
    try:
        rxcui = await _exact_rxcui(query, client) or await _approx_rxcui(query, client)
        if not rxcui:
            return None
        name = await _name_for_rxcui(rxcui, client) or query
        return RxNormMatch(rxcui=rxcui, name=name)
    finally:
        if own_client:
            await client.aclose()


@async_lru_cache(maxsize=1)
async def _load_display_names(*, client: httpx.AsyncClient | None = None) -> tuple[str, ...]:
    """Fetch RxNorm's full display-name list once (what RxNav's own autocomplete uses).

    It's ~28k clean drug names in a single response, so we pull it once and cache
    it in-process, then prefix-filter locally per keystroke rather than hitting
    RxNorm on every request.
    """
    own_client = client is None
    client = client or httpx.AsyncClient(base_url=settings.rxnorm_base_url, timeout=10.0)
    try:
        r = await client.get("/displaynames.json")
        r.raise_for_status()
        terms = r.json().get("displayTermsList", {}).get("term") or []
        return tuple(terms)
    finally:
        if own_client:
            await client.aclose()


async def suggest_names(
    prefix: str, *, limit: int = 10, client: httpx.AsyncClient | None = None
) -> list[str]:
    """Autocomplete drug names: prefix matches first, then other substring matches."""
    prefix = prefix.strip().lower()
    if not prefix:
        return []
    terms = await _load_display_names(client=client)
    starts: list[str] = []
    contains: list[str] = []
    for term in terms:
        lowered = term.lower()
        if lowered.startswith(prefix):
            starts.append(term)
        elif prefix in lowered:
            contains.append(term)
    # Shorter names first surfaces the plain ingredient ("ibuprofen") ahead of its
    # combination products ("ibuprofen / pseudoephedrine"); ties broken alphabetically.
    starts.sort(key=lambda t: (len(t), t.lower()))
    contains.sort(key=lambda t: (len(t), t.lower()))
    return (starts + contains)[:limit]
