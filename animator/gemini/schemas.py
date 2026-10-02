"""Structured-output models Gemini fills in."""
from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, Field

from ..regions import Box, RegionRole, RevealStyle


class Beat(BaseModel):
    label: str = Field(description="1-3 word caption written next to the icon, e.g. 'SUNLIGHT'.")
    visual: str = Field(description="The ONE simple icon drawn during this sentence, e.g. 'yellow sun with short rays'.")
    narration: str = Field(description="One spoken sentence that says the label's words out loud.")

    @property
    def label_is_spoken(self) -> bool:
        spoken = re.sub(r"[^a-z ]", "", self.narration.lower())
        words = re.sub(r"[^a-z ]", "", self.label.lower()).split()
        return all(word.rstrip("s") in spoken for word in words)


class StoryboardScene(BaseModel):
    title: str = Field(description="2-4 word scene heading written at the top of the frame.")
    beats: List[Beat] = Field(description="3-5 beats, in the order they are spoken and drawn.")
    layout: str = Field(description="Where each icon sits and which arrows connect which icons.")

    @property
    def narration(self) -> str:
        return " ".join(beat.narration.strip() for beat in self.beats)


class StoryboardPlan(BaseModel):
    title: str
    scenes: List[StoryboardScene]


class DetectedRegion(BaseModel):
    label: str = Field(description="Short slug describing the region's content, e.g. 'title', 'co2_arrow'.")
    role: RegionRole
    object: str = Field(description="Short description of the exact thing in this region.")
    reveal_order: int = Field(description="1-indexed draw order. UNIQUE across the array.")
    box: Box = Field(description="Named normalized bounding box: ymin/xmin/ymax/xmax, each 0-1000.")
    annotation: str = Field(
        default="",
        description="Transcript phrase or short paraphrase spoken while this region should draw.",
    )
    reveal: RevealStyle = Field(description="Reveal style hint: 'stroke', 'fill', or 'fade'.")
    beat: int = Field(default=0, description="1-indexed narration beat this region draws in; 0 when no beats are given.")


class DetectionResponse(BaseModel):
    regions: List[DetectedRegion]
