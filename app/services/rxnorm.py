"""Normalize free-text drug names to RxCUI codes via NIH RxNorm (free, no auth)."""

from dataclasses import dataclass

import httpx

from app.cache import async_lru_cache
from app.config import settings


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
