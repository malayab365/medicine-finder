"""Search endpoints: name lookup (public) and symptom triage (gated + rate-limited)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.deps import require_user
from app.core.clients import Clients, get_clients
from app.core.config import settings
from app.medicines import service
from app.medicines.schemas import (
    NameSearchRequest,
    NameSearchResponse,
    SymptomSearchRequest,
    SymptomSearchResponse,
)
from app.shared.ratelimit import FixedWindowRateLimiter, rate_limit

router = APIRouter(prefix="/search", tags=["search"])

name_limiter = FixedWindowRateLimiter(limit=settings.name_rate_limit_per_minute)
symptom_limiter = FixedWindowRateLimiter(limit=settings.symptom_rate_limit_per_minute)


@router.post(
    "/name",
    response_model=NameSearchResponse,
    dependencies=[Depends(rate_limit(name_limiter))],
)
async def search_name(
    req: NameSearchRequest, clients: Annotated[Clients, Depends(get_clients)]
) -> NameSearchResponse:
    return await service.search_by_name(req.query, clients)


@router.post(
    "/symptom",
    response_model=SymptomSearchResponse,
    dependencies=[Depends(rate_limit(symptom_limiter)), Depends(require_user)],
)
async def search_symptom(
    req: SymptomSearchRequest, clients: Annotated[Clients, Depends(get_clients)]
) -> SymptomSearchResponse:
    return await service.search_by_symptom(req.symptoms, clients)
