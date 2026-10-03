"""GET /api/health: is this server able to generate videos right now?"""

import shutil

from fastapi import APIRouter

from ..schemas import HealthResponse
from ..settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    checks = {
        "ffmpeg": shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None,
        "gemini_configured": bool(settings.gemini_api_key),
        "supabase_configured": bool(settings.supabase_url and settings.supabase_secret_key),
    }
    return HealthResponse(status="ok" if all(checks.values()) else "degraded", **checks)
