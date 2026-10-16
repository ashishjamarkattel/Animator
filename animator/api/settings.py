"""Server configuration, read once from the environment and the repo's .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_secret_key: str
    allowed_origins: list[str]
    max_concurrent_jobs: int


@lru_cache
def get_settings() -> Settings:
    # finds the repo's .env from this file's folder, so plain `uvicorn ...` works without --env-file;
    # variables already set in the environment win
    load_dotenv()
    origins = os.environ.get("API_ALLOWED_ORIGINS", "http://localhost:5173")
    return Settings(
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        # the secret (service-role) key: it bypasses row-level security, so it only ever lives on the server
        supabase_secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
        allowed_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        max_concurrent_jobs=int(os.environ.get("API_MAX_CONCURRENT_JOBS", "1")),
    )
