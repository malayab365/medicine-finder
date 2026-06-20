"""Operational endpoints with no business logic: health check and robots.txt."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["system"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots() -> str:
    # Block indexing while in v1 (informational, not medical advice).
    return "User-agent: *\nDisallow: /\n"
