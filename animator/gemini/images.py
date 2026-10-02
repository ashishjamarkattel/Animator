"""STEP 2: draw one storyboard scene as a 16:9 whiteboard image."""
from __future__ import annotations

from google import genai
from google.genai import types

from ..prompts import load_prompt
from .client import first_inline_data, with_retry
from .schemas import StoryboardScene
from .settings import DEFAULT_IMAGE_MODEL


def build_image_prompt(scene: StoryboardScene) -> str:
    elements = "\n".join(
        f'{index}. {beat.visual.strip()} — caption "{beat.label.strip().upper()}"'
        for index, beat in enumerate(scene.beats, start=1)
    )
    frame = load_prompt("scene_image").format(
        title=scene.title.strip().upper(),
        count=len(scene.beats),
        elements=elements,
        layout=scene.layout.strip(),
    )
    return f"{frame}\n{load_prompt('image_style')}"


def generate_scene_image(
    google_client: genai.Client,
    scene: StoryboardScene,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
) -> bytes:
    """Render one frame of separate flat doodle icons. Returns image bytes."""
    response = with_retry(lambda: google_client.models.generate_content(
        model=model,
        contents=build_image_prompt(scene),
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="16:9"),
        ),
    ))
    return first_inline_data(response, "Image generation")
