"""STEP 4: detect a region plan (what to draw, where, and when) from a
finished whiteboard image."""
from __future__ import annotations

from pathlib import Path
from typing import List

from google import genai
from google.genai import types
from PIL import Image

from ..prompts import load_prompt
from ..regions import Region, SnippetRegionPlan
from .client import with_retry_async
from .schemas import DetectedRegion, DetectionResponse
from .settings import DEFAULT_REGION_MODEL


def build_region_prompt(transcript_text: str, idea: str, beats: List[str] | None = None) -> str:
    prompt = load_prompt("region_detection").format(idea=idea, transcript_text=transcript_text)
    if not beats:
        return prompt
    numbered = "\n".join(f"  {index}. {text}" for index, text in enumerate(beats, start=1))
    return f"{prompt}\n\n{load_prompt('region_beats').format(numbered=numbered)}"


def to_region(detected: DetectedRegion) -> Region:
    return Region(
        label=detected.label,
        role=detected.role,
        object=detected.object,
        reveal_order=detected.reveal_order,
        box=detected.box,
        expected_visual=detected.object,
        annotation=detected.annotation,
        reveal=detected.reveal,
        beat=detected.beat or None,
    )


async def detect_region_plan(
    *,
    google_client: genai.Client,
    image_path: Path,
    transcript_text: str,
    idea: str = "",
    model: str = DEFAULT_REGION_MODEL,
    beats: List[str] | None = None,
) -> SnippetRegionPlan:
    idea = idea or "(untitled)"
    with Image.open(image_path) as image:
        size = list(image.size)
        mime_type = Image.MIME.get(image.format, "image/png")

    response = await with_retry_async(lambda: google_client.aio.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime_type),
            build_region_prompt(transcript_text, idea, beats),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DetectionResponse,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    ))
    parsed: DetectionResponse | None = response.parsed if response else None
    if parsed is None or not parsed.regions:
        raise RuntimeError(f"Region detection returned no regions. raw: {(response.text or '')[:500]}")

    return SnippetRegionPlan(
        idea=idea,
        global_style_notes="",
        regions=[to_region(detected) for detected in parsed.regions],
        image_size=size,
    )
