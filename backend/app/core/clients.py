"""Shared, long-lived HTTP clients for the external REST APIs.

Previously each RxNorm / OpenFDA call opened and closed its own
`httpx.AsyncClient`, throwing away connection pooling (a symptom search with 5
candidates meant ~10+ fresh TLS handshakes). These clients are created once in
the app lifespan and injected into request handlers via `get_clients`, so
connections are reused across requests.

The OpenAI/OpenRouter client is intentionally *not* held here: constructing
`AsyncOpenAI` requires a non-empty API key, and eagerly building it would break
name-search-only deployments and the test suite (where the triage call is
stubbed). The triage provider builds its own client lazily when it actually runs.
"""

from dataclasses import dataclass

import httpx
from starlette.requests import Request

from app.core.config import settings


@dataclass
class Clients:
    rxnorm: httpx.AsyncClient
    openfda: httpx.AsyncClient


def create_clients() -> Clients:
    return Clients(
        rxnorm=httpx.AsyncClient(base_url=settings.rxnorm_base_url, timeout=10.0),
        openfda=httpx.AsyncClient(base_url=settings.openfda_base_url, timeout=10.0),
    )


async def close_clients(clients: Clients) -> None:
    await clients.rxnorm.aclose()
    await clients.openfda.aclose()


def get_clients(request: Request) -> Clients:
    """FastAPI dependency: the shared client container.

    The lifespan stores it on `app.state`. Lazily create it as a fallback so the
    dependency still works when the app is used without its lifespan running
    (e.g. a bare `TestClient(app)` that isn't entered as a context manager).
    """
    clients = getattr(request.app.state, "clients", None)
    if clients is None:
        clients = create_clients()
        request.app.state.clients = clients
    return clients
