"""
Custom exception hierarchy and global FastAPI exception handlers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


class EDDServiceError(Exception):
    def __init__(
        self,
        detail: str = "internal_error",
        message: str = "An unexpected error occurred.",
        status_code: int = 500,
    ) -> None:
        self.detail = detail
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class FixtureNotFoundError(EDDServiceError):
    def __init__(self, fixture_id: str) -> None:
        super().__init__(
            detail="fixture_not_found",
            message=f"No fixture found with ID '{fixture_id}'.",
            status_code=404,
        )


class AnalysisError(EDDServiceError):
    def __init__(self, message: str = "Analysis pipeline failed.") -> None:
        super().__init__(detail="analysis_error", message=message, status_code=500)


class ClaudeAPIError(EDDServiceError):
    def __init__(self, message: str = "Claude API call failed.") -> None:
        super().__init__(detail="claude_api_error", message=message, status_code=502)


def register_exception_handlers(app: "FastAPI") -> None:
    @app.exception_handler(EDDServiceError)
    async def _handle_domain_error(request: Request, exc: EDDServiceError) -> JSONResponse:
        logger.warning("Domain error: %s — %s", exc.detail, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception during %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal_error", "message": "An unexpected error occurred."},
        )
