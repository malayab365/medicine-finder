"""Composition root: assemble the app from its feature modules.

Each feature lives in its own package (`auth`, `medicines`, `system`) and exposes
an `APIRouter`. Adding a feature means dropping in a new package and one
`include_router` line here — no edits to the existing modules.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import repository
from app.auth.router import router as auth_router
from app.core.clients import close_clients, create_clients
from app.core.logging import configure_logging
from app.core.middleware import install_middleware
from app.medicines.router import router as medicines_router
from app.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    repository.init_db()
    app.state.clients = create_clients()
    try:
        yield
    finally:
        await close_clients(app.state.clients)


def create_app() -> FastAPI:
    app = FastAPI(title="Medicine Search API", version="0.3.0", lifespan=lifespan)
    install_middleware(app)
    app.include_router(system_router)
    app.include_router(auth_router)
    app.include_router(medicines_router)
    return app


app = create_app()
