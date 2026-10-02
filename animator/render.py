"""File-level rendering: one image (plus optional audio) to an MP4, and
several such scenes concatenated into one video."""

from __future__ import annotations

import os
import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .engine import Animator
from .regions import SnippetRegionPlan, build_narration_weighted_plan

QUALITY = {
    "low": {"fps": 20, "bitrate": "500k"},
    "medium": {"fps": 24, "bitrate": "1500k"},
    "high": {"fps": 24, "bitrate": "3000k"},
}


@dataclass
class Scene:
    image: str | Path
    audio: str | Path | None = None
    duration: float | None = None
    region_plan: SnippetRegionPlan | None = None


def probe_duration(media_path: str | Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(media_path)],
        check=True, capture_output=True, text=True,
    )
    try:
        duration = float(out.stdout.strip())
    except ValueError as exc:
        raise ValueError(f"cannot determine duration of audio '{media_path}'") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"audio '{media_path}' must have a finite duration greater than zero")
    return duration


def render_scene(
    scene: Scene,
    output_path: str | Path,
    *,
    quality: str = "medium",
    animator: Animator | None = None,
) -> float:
    """Render one scene to an MP4. Returns the scene duration in seconds.

    With audio, the drawing finishes inside the audio and the rest holds the
    finished frame. With a region plan, regions draw in narration-weighted
    windows; otherwise the whole image draws over 70% of the duration.
    """
    if scene.audio is None and scene.duration is None:
        raise ValueError("scene needs audio or duration")
    duration = scene.duration if scene.audio is None else probe_duration(scene.audio)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("scene duration must be a finite number greater than zero")

    element_plan = None
    if scene.region_plan is not None:
        element_plan = build_narration_weighted_plan(scene.region_plan, duration)
    if animator is None:
        animator = Animator(fade_duration=0.06 if element_plan else 0.12)

    with Image.open(scene.image) as image:
        # Normalize palette, grayscale, and transparent images to ink on white.
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", image.size, "white")
        img_array = np.array(Image.alpha_composite(background, rgba).convert("RGB"))
    settings = QUALITY.get(quality, QUALITY["medium"])
    output_path = str(output_path)

    if scene.audio is None:
        animator.render_to_file(
            img_array, duration * 0.7, duration, output_path,
            element_plan=element_plan, **settings,
        )
        return duration

    video_only = output_path + ".video_only.mp4"
    animator.render_to_file(
        img_array, duration * 0.7, duration, video_only,
        element_plan=element_plan, **settings,
    )
    del img_array
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_only, "-i", str(scene.audio),
             "-c:v", "copy", "-c:a", "aac", output_path],
            check=True, capture_output=True,
        )
    finally:
        try:
            os.unlink(video_only)
        except OSError:
            pass
    return duration


def concatenate(paths: list[str | Path], output_path: str | Path) -> None:
    """Join MP4 segments without re-encoding."""
    output_path = str(output_path)
    concat_list = output_path + ".concat.txt"
    try:
        with open(concat_list, "w") as f:
            for p in paths:
                f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c", "copy", output_path],
            check=True, capture_output=True,
        )
    finally:
        if os.path.exists(concat_list):
            os.remove(concat_list)


def render_video(
    scenes: list[Scene],
    output_path: str | Path,
    *,
    quality: str = "medium",
) -> list[float]:
    """Render every scene and concatenate them. Returns per-scene durations.

    Every scene must have audio or none of them may, since ffmpeg concat
    needs matching streams.
    """
    if not scenes:
        raise ValueError("no scenes")
    with_audio = {scene.audio is not None for scene in scenes}
    if len(with_audio) > 1:
        raise ValueError("either every scene has audio or none does")
    if len(scenes) == 1:
        return [render_scene(scenes[0], output_path, quality=quality)]

    animator = None
    durations = []
    with tempfile.TemporaryDirectory() as temp_dir:
        segments = []
        for index, scene in enumerate(scenes):
            plan = build_narration_weighted_plan(scene.region_plan, 1.0) if scene.region_plan else None
            if animator is None or (animator.fade_duration == 0.12) == bool(plan):
                animator = Animator(fade_duration=0.06 if plan else 0.12)
            segment = os.path.join(temp_dir, f"segment_{index:03d}.mp4")
            durations.append(render_scene(scene, segment, quality=quality, animator=animator))
            segments.append(segment)
        concatenate(segments, output_path)
    return durations
