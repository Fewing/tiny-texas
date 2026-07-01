from __future__ import annotations

import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/tiny_texas.db")
    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "tiny_texas_session")
    session_days: int = int(os.getenv("SESSION_DAYS", "14"))
    cookie_secure: bool = _bool_env("COOKIE_SECURE", False)
    allowed_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    )


settings = Settings()

