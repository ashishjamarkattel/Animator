"""Request and response bodies for the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

VideoStatus = Literal["queued", "generating", "ready", "failed"]


class GenerateRequest(BaseModel):
    video_id: str


class GenerateResponse(BaseModel):
    video_id: str
    status: VideoStatus
    credits_charged: int


class VideoResponse(BaseModel):
    id: str
    prompt: str
    status: VideoStatus
    scenes: int | None
    voice: str
    quality: str
    storage_path: str | None
    duration_seconds: float | None
    error: str | None
    created_at: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ffmpeg: bool
    gemini_configured: bool
    supabase_configured: bool
