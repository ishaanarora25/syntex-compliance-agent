"""
Application configuration loaded from environment variables.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"
    ANTHROPIC_AGENT_MODEL: str = "claude-opus-4-7"
    AGENT_MAX_ITERATIONS: int = 30
    AGENT_TOOL_TIMEOUT_S: int = 60

    # Optional override for the Claude Code CLI binary the SDK shells out to.
    # The SDK ships an x86_64 build that crashes on AVX-less / Rosetta-served
    # macOS — set this to a native install (e.g. /Users/me/.local/bin/claude)
    # to bypass the bundled binary.
    CLAUDE_CLI_PATH: str | None = None

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3001"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
