"""One generation job, run in a background thread after POST /api/generate.

    STEP 1  wait for a free slot (generation is CPU-heavy, so jobs run a few at a time)
    STEP 2  render the video from the prompt with the existing storyboard pipeline
    STEP 3  upload the MP4 to the private "videos" storage bucket
    STEP 4  mark the video ready, and refund credits for scenes that weren't used

Any failure marks the video failed with a readable reason and refunds the full charge.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from functools import cache
from pathlib import Path

from google import genai

from ..cli import resolve_model, resolve_region_model
from ..gemini.pipeline import StoryboardOptions, run_storyboard
from ..gemini.settings import DEFAULT_IMAGE_MODEL, DEFAULT_TEXT_MODEL, DEFAULT_TTS_MODEL
from . import supabase
from .settings import get_settings

log = logging.getLogger(__name__)



@cache
def _slots() -> threading.BoundedSemaphore:
    # created on first use, not at import: settings must be read after .env is loaded
    return threading.BoundedSemaphore(get_settings().max_concurrent_jobs)


def run_job(video: dict, credits_charged: int) -> None:
    try:
        with _slots():  # STEP 1
            with tempfile.TemporaryDirectory() as temp_dir:
                output = Path(temp_dir) / "video.mp4"
                durations = _render(video, output)  # STEP 2
                storage_path = f"{video['user_id']}/{video['id']}.mp4"
                supabase.upload_video(storage_path, output)  # STEP 3
        _finish(video, storage_path, durations, credits_charged)  # STEP 4
    except Exception as exc:
        log.exception("video %s failed", video["id"])
        supabase.update_video(video["id"], {"status": "failed", "error": _reason(exc)})
        supabase.refund_credits(video["user_id"], credits_charged)


def _render(video: dict, output: Path) -> list[float]:
    options = StoryboardOptions(
        idea=video["prompt"],
        output=output,
        quality=video["quality"],
        text_model=resolve_model(None, DEFAULT_TEXT_MODEL),
        region_model=resolve_region_model(None),
        image_model=DEFAULT_IMAGE_MODEL,
        tts_model=DEFAULT_TTS_MODEL,
        voice=video["voice"],
        num_scenes=video["scenes"],
    )
    return run_storyboard(genai.Client(api_key=get_settings().gemini_api_key), options)


def _finish(video: dict, storage_path: str, durations: list[float], credits_charged: int) -> None:
    supabase.update_video(
        video["id"],
        {"status": "ready", "storage_path": storage_path, "duration_seconds": round(sum(durations), 2), "error": None},
    )
    used = len(durations) * get_settings().credits_per_scene
    supabase.refund_credits(video["user_id"], credits_charged - used)


def _reason(exc: Exception) -> str:
    """A short message the user sees in their video list; details stay in the server log."""
    text = str(exc).lower()
    if "429" in text or "resource_exhausted" in text or "quota" in text:
        return "The AI service is busy. Try again in a few minutes."
    if "safety" in text or "blocked" in text:
        return "This topic was blocked by the AI's safety filter. Try rephrasing it."
    return "Generation failed. Try again, or try a shorter prompt."
