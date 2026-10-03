"""Server configuration, read once from the environment (.env is loaded by __main__)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_secret_key: str
    gemini_api_key: str
    allowed_origins: list[str]
    max_concurrent_jobs: int
    credits_per_scene: int
    auto_scene_estimate: int


@lru_cache
def get_settings() -> Settings:
    origins = os.environ.get("API_ALLOWED_ORIGINS", "http://localhost:5173")
    return Settings(
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        # the secret (service-role) key: it bypasses row-level security, so it only ever lives on the server
        supabase_secret_key=os.environ.get("SUPABASE_SECRET_KEY", ""),
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "",
        allowed_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
        max_concurrent_jobs=int(os.environ.get("API_MAX_CONCURRENT_JOBS", "1")),
        credits_per_scene=int(os.environ.get("API_CREDITS_PER_SCENE", "2")),
        # "Auto" lets Gemini pick the scene count, so charge for this many up front and refund the rest
        auto_scene_estimate=int(os.environ.get("API_AUTO_SCENE_ESTIMATE", "6")),
    )
