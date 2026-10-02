"""Turn a whiteboard-style image into a hand-drawn reveal video."""

from .engine import Animator
from .regions import Box, Region, SnippetRegionPlan, build_narration_weighted_plan
from .render import Scene, render_scene, render_video

__all__ = [
    "Box",
    "Region",
    "Scene",
    "SnippetRegionPlan",
    "Animator",
    "build_narration_weighted_plan",
    "render_scene",
    "render_video",
]
