"""
FastAPI application entry point for Syntex Compliance Agent (EDD).

Creates the ASGI application with:
- CORS middleware configured from environment settings
- Structured logging initialised at startup via the lifespan hook
- A health-check endpoint at /health
- EDD router mounted under /api
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.exceptions import register_exception_handlers
from app.routers import edd


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Syntex Compliance Agent (EDD Service)")
    yield
    logger.info("Shutting down Syntex Compliance Agent")


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Syntex Compliance Agent — EDD Service",
        description="AI-native Enhanced Due Diligence: UBO resolution, trust look-through, OFAC screening, memo drafting.",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)
    application.include_router(edd.router)

    @application.get("/health", tags=["health"])
    async def health_check() -> Dict[str, str]:
        return {"status": "healthy"}

    return application


app = create_app()
