"""STEP 5 orchestrator for --prompt: idea -> storyboard -> per-scene image,
narration and regions -> one rendered video. Start reading here."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from google import genai

from ..render import Scene, render_video
from .detect_regions import detect_region_plan
from .images import generate_scene_image
from .narration import generate_beat_narration
from .schemas import StoryboardScene
from .storyboard import generate_storyboard


@dataclass
class StoryboardOptions:
    idea: str
    output: Path
    quality: str
    text_model: str
    region_model: str
    image_model: str
    tts_model: str
    voice: str
    num_scenes: Optional[int] = None
    save_assets: bool = False


async def build_scene(
    google_client: genai.Client,
    options: StoryboardOptions,
    asset_dir: Path,
    index: int,
    scene: StoryboardScene,
) -> Scene:
    """Image and narration in parallel, then regions, which need both the
    image and the beats."""
    beats = [beat.narration for beat in scene.beats]
    image_bytes, (audio_bytes, beat_windows) = await asyncio.gather(
        asyncio.to_thread(generate_scene_image, google_client, scene, model=options.image_model),
        asyncio.to_thread(
            generate_beat_narration, google_client, beats, model=options.tts_model, voice=options.voice,
        ),
    )
    image_path = asset_dir / f"scene_{index:02d}.png"
    image_path.write_bytes(image_bytes)
    audio_path = asset_dir / f"scene_{index:02d}.wav"
    audio_path.write_bytes(audio_bytes)

    region_plan = await detect_region_plan(
        google_client=google_client,
        image_path=image_path,
        transcript_text=scene.narration,
        idea=scene.title,
        model=options.region_model,
        beats=beats,
    )
    region_plan.beat_windows = beat_windows
    if options.save_assets:
        region_path = asset_dir / f"scene_{index:02d}.regions.json"
        region_path.write_text(region_plan.model_dump_json(indent=2))
    print(f"  scene {index + 1} ready: {scene.title}", file=sys.stderr)
    return Scene(image=str(image_path), audio=str(audio_path), region_plan=region_plan)


async def render_storyboard(
    google_client: genai.Client,
    options: StoryboardOptions,
    asset_dir: Path,
) -> List[float]:
    # STEP 1
    print(f"generating storyboard for: {options.idea!r}", file=sys.stderr)
    plan = generate_storyboard(
        google_client, options.idea, model=options.text_model, num_scenes=options.num_scenes,
    )
    print(f"storyboard: {len(plan.scenes)} scene(s)", file=sys.stderr)
    if options.save_assets:
        (asset_dir / "storyboard.json").write_text(plan.model_dump_json(indent=2))

    # STEPS 2-4, all scenes concurrently
    scenes = await asyncio.gather(
        *(build_scene(google_client, options, asset_dir, index, scene) for index, scene in enumerate(plan.scenes))
    )
    # STEP 5
    return render_video(scenes, str(options.output), quality=options.quality)


def run_storyboard(google_client: genai.Client, options: StoryboardOptions) -> List[float]:
    """Keep assets next to the output when asked, otherwise in a temp dir."""
    if options.save_assets:
        asset_dir = options.output.parent / f"{options.output.stem}.storyboard"
        asset_dir.mkdir(parents=True, exist_ok=True)
        return asyncio.run(render_storyboard(google_client, options, asset_dir))
    with tempfile.TemporaryDirectory() as temp_dir:
        return asyncio.run(render_storyboard(google_client, options, Path(temp_dir)))
