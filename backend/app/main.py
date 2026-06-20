from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware

from app import auth, db
from app.config import settings
from app.ratelimit import FixedWindowRateLimiter
from app.schemas import (
    EMERGENCY_MESSAGE,
    AuthRequest,
    Candidate,
    NameSearchRequest,
    NameSearchResponse,
    SymptomSearchRequest,
    SymptomSearchResponse,
    UserResponse,
)
from app.services.openfda import fetch_adverse_events, fetch_label
from app.services.rxnorm import normalize_name
from app.services.triage import is_emergency, triage


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Medicine Search API", version="0.2.0", lifespan=lifespan)

# Cross-origin support for the Next.js frontend. With the dev proxy (Next.js
# rewrites) requests are same-origin and this isn't strictly needed, but it keeps
# direct cross-origin calls working too. Credentials are required for the cookie.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

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


# --- Auth (JSON) ---------------------------------------------------------


@app.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(req: AuthRequest, request: Request) -> UserResponse:
    error = auth.validate_credentials(req.username, req.password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    try:
        user = auth.register_user(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    request.session["user_id"] = user["id"]
    return UserResponse(id=user["id"], username=user["username"])


@app.post("/auth/login", response_model=UserResponse)
async def login(req: AuthRequest, request: Request) -> UserResponse:
    user = auth.authenticate(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session["user_id"] = user["id"]
    return UserResponse(id=user["id"], username=user["username"])


@app.post("/auth/logout", status_code=204)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@app.get("/auth/me", response_model=UserResponse)
async def me(user: Annotated[dict, Depends(auth.require_user)]) -> UserResponse:
    return UserResponse(id=user["id"], username=user["username"])


# --- Search --------------------------------------------------------------


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
    dependencies=[Depends(rate_limit(symptom_limiter)), Depends(auth.require_user)],
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
