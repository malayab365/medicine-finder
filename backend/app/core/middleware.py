"""Framework middleware wiring (CORS + sessions), kept out of the route modules."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings


def install_middleware(app: FastAPI) -> None:
    # Cross-origin support for the Next.js frontend. With the dev proxy (Next.js
    # rewrites) requests are same-origin and this isn't strictly needed, but it
    # keeps direct cross-origin calls working too. Credentials carry the cookie.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
