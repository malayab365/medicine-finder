from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.ratelimit import FixedWindowRateLimiter
from app.schemas import (
    EMERGENCY_MESSAGE,
    Candidate,
    NameSearchRequest,
    NameSearchResponse,
    SymptomSearchRequest,
    SymptomSearchResponse,
)
from app.services.openfda import fetch_adverse_events, fetch_label
from app.services.rxnorm import normalize_name
from app.services.triage import is_emergency, triage

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Medicine Search", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

name_limiter = FixedWindowRateLimiter(limit=settings.name_rate_limit_per_minute)
symptom_limiter = FixedWindowRateLimiter(limit=settings.symptom_rate_limit_per_minute)


def rate_limit(limiter: FixedWindowRateLimiter):
    def dependency(request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        allowed, retry_after = limiter.check(key)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots() -> str:
    # Block indexing while in v1 (informational, not medical advice).
    return "User-agent: *\nDisallow: /\n"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post(
    "/search/name",
    response_model=NameSearchResponse,
    dependencies=[Depends(rate_limit(name_limiter))],
)
async def search_name(req: NameSearchRequest) -> NameSearchResponse:
    match = await normalize_name(req.query)
    rxcui = match.rxcui if match else None
    matched_name = match.name if match else None
    label = await fetch_label(rxcui=rxcui, name=matched_name or req.query)
    adverse_events = await fetch_adverse_events(rxcui=rxcui, name=matched_name or req.query)
    return NameSearchResponse(
        query=req.query,
        matched_name=matched_name,
        rxcui=rxcui,
        label=label,
        adverse_events=adverse_events,
    )


@app.post(
    "/search/symptom",
    response_model=SymptomSearchResponse,
    dependencies=[Depends(rate_limit(symptom_limiter))],
)
async def search_symptom(req: SymptomSearchRequest) -> SymptomSearchResponse:
    # Hard-coded emergency check runs before any LLM call.
    if is_emergency(req.symptoms):
        return SymptomSearchResponse(emergency=True, message=EMERGENCY_MESSAGE)

    result = await triage(req.symptoms)
    if result.emergency:
        return SymptomSearchResponse(emergency=True, message=EMERGENCY_MESSAGE)

    candidates: list[Candidate] = []
    for name in result.candidates:
        match = await normalize_name(name)
        rxcui = match.rxcui if match else None
        matched_name = match.name if match else None
        label = await fetch_label(rxcui=rxcui, name=matched_name or name)
        candidates.append(
            Candidate(name=name, matched_name=matched_name, rxcui=rxcui, label=label)
        )
    return SymptomSearchResponse(candidates=candidates)
