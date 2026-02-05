from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.settings import get_settings
from app.db.deps import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure engine is created at startup; dispose at shutdown.
    engine = get_engine()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Cyberxercise API", lifespan=lifespan)

    origins = [o.strip() for o in (settings.cors_origins or "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"] ,
            allow_headers=["*"] ,
        )

    app.include_router(api_router)
    return app


app = create_app()
