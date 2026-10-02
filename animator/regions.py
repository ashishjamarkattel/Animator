"""Region plans: how one image is decomposed into ordered drawing acts.

A plan lists regions (bounding box, reveal order, associated narration text).
The animator estimates time windows from text length and box area; these are
not timestamps aligned to the audio.

The planner uses Google's object-detection convention:
`box_2d` is [ymin, xmin, ymax, xmax] normalized to 0-1000, relative to the
eventual image dimensions. Convert it to pixel [x1, y1, x2, y2] only at the
point of use.
"""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

CANVAS_W = 1536
CANVAS_H = 1024

RegionRole = Literal[
    "title",
    "main_concept",
    "supporting_detail",
    "annotation",
    "label",
    "decoration",
]

RevealStyle = Literal["stroke", "fill", "fade"]


class Box(BaseModel):
    """Region bounding box in normalized 0-1000 coordinates with named fields.

    Named fields eliminate the ordering ambiguity of a positional [ymin, xmin,
    ymax, xmax] list (some models flip into [xmin, ymin, ...] form). Origin is
    top-left: y=0 is the top edge, y=1000 is the bottom edge.
    """
    ymin: int = Field(ge=0, le=1000, description="Top edge (0=top, 1000=bottom).")
    xmin: int = Field(ge=0, le=1000, description="Left edge (0=left, 1000=right).")
    ymax: int = Field(ge=0, le=1000, description="Bottom edge. Must be > ymin.")
    xmax: int = Field(ge=0, le=1000, description="Right edge. Must be > xmin.")


class Region(BaseModel):
    label: str = Field(description="Short identifier, e.g. 'title', 'cell_diagram', 'arrow_to_output'")
    role: RegionRole
    object: str = Field(
        default="",
        description="The concrete drawable object or element, e.g. 'large cell outline', 'red arrow', 'yield curve'.",
    )
    reveal_order: int = Field(description="1-indexed draw order within this snippet. Unique.")
    box: Optional[Box] = Field(
        default=None,
        description="Bounding box with named ymin/xmin/ymax/xmax fields in normalized 0-1000.",
    )
    box_2d: List[int] = Field(
        default_factory=list,
        description="Legacy [ymin, xmin, ymax, xmax] list form. Prefer `box`.",
        max_length=4,
    )
    bbox: Optional[List[int]] = Field(
        default=None,
        description=(
            "Legacy pixel fallback [x1, y1, x2, y2]. New planner outputs should use box_2d instead."
        ),
        min_length=4, max_length=4,
    )
    location: str = Field(
        default="",
        description="Natural-language placement derived from box_2d, e.g. 'upper-left', 'center-right, large'.",
    )
    expected_visual: str = Field(description="One sentence describing what to draw in this region.")
    annotation: str = Field(
        default="",
        description=(
            "Literal narration spoken while this region draws. May be empty when "
            "the region is detected from a pre-existing image without per-region transcript."
        ),
    )
    reveal: RevealStyle = Field(
        default="stroke",
        description=(
            "Suggested reveal style for this region. 'stroke' for outlines/text, "
            "'fill' for solid filled shapes, 'fade' for backgrounds/decoration."
        ),
    )
    beat: Optional[int] = Field(
        default=None,
        description="1-indexed narration beat during which this region draws. See SnippetRegionPlan.beat_windows.",
    )

    @model_validator(mode="after")
    def ensure_box_source(self):
        if self.box is None and not self.box_2d and self.bbox is None:
            raise ValueError("Region requires box, box_2d, or legacy bbox")
        # If only the list form was supplied, hydrate `box` for downstream use.
        if self.box is None and self.box_2d and len(self.box_2d) == 4:
            ymin, xmin, ymax, xmax = self.box_2d
            self.box = Box(ymin=ymin, xmin=xmin, ymax=ymax, xmax=xmax)
        return self

    def pixel_bbox(self, width: int, height: int) -> List[int]:
        """Return [x1, y1, x2, y2] pixels for a target image size."""
        if self.box is not None:
            x1 = int(self.box.xmin / 1000 * width)
            y1 = int(self.box.ymin / 1000 * height)
            x2 = int(self.box.xmax / 1000 * width)
            y2 = int(self.box.ymax / 1000 * height)
            return ensure_pixel_box([x1, y1, x2, y2], width, height)
        if self.box_2d:
            return descale_box_2d(self.box_2d, width, height)

        x1, y1, x2, y2 = self.bbox or [0, 0, 1, 1]
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        x1 = max(0, min(width, int(x1 / CANVAS_W * width)))
        x2 = max(0, min(width, int(x2 / CANVAS_W * width)))
        y1 = max(0, min(height, int(y1 / CANVAS_H * height)))
        y2 = max(0, min(height, int(y2 / CANVAS_H * height)))
        return ensure_pixel_box([x1, y1, x2, y2], width, height)


def ensure_pixel_box(box: List[int], width: int, height: int) -> List[int]:
    x1, y1, x2, y2 = box
    x1, x2 = sorted((int(x1), int(x2)))
    y1, y2 = sorted((int(y1), int(y2)))
    x1 = max(0, min(width, x1))
    x2 = max(0, min(width, x2))
    y1 = max(0, min(height, y1))
    y2 = max(0, min(height, y2))
    if x2 <= x1:
        if x1 >= width:
            x1 = max(0, width - 1)
        x2 = min(width, x1 + 1)
    if y2 <= y1:
        if y1 >= height:
            y1 = max(0, height - 1)
        y2 = min(height, y1 + 1)
    return [x1, y1, x2, y2]


def descale_box_2d(box_2d: List[int], width: int, height: int) -> List[int]:
    """Convert [ymin, xmin, ymax, xmax] normalized 0-1000 to [x1, y1, x2, y2] pixels."""
    ymin, xmin, ymax, xmax = box_2d
    x1 = int(xmin / 1000 * width)
    y1 = int(ymin / 1000 * height)
    x2 = int(xmax / 1000 * width)
    y2 = int(ymax / 1000 * height)
    return ensure_pixel_box([x1, y1, x2, y2], width, height)


class SnippetRegionPlan(BaseModel):
    """One idea = one image = one set of regions."""
    idea: str = Field(description="Short title for the idea (3-8 words).")
    global_style_notes: str = Field(default="", description="Free-text style guidance for this image.")
    regions: List[Region]
    image_size: List[int] = Field(
        default_factory=lambda: [CANVAS_W, CANVAS_H],
        description="[width, height] of the reference image. Used for legacy bbox compatibility.",
        min_length=2, max_length=2,
    )
    beat_windows: Optional[List[List[float]]] = Field(
        default=None,
        description=(
            "Measured [start, end] seconds of each narration beat in the scene audio. "
            "When set, regions draw inside the window of their `beat` instead of "
            "in estimated slots."
        ),
    )

    @property
    def transcript_text(self) -> str:
        return " ".join(
            r.annotation.strip()
            for r in sorted(self.regions, key=lambda x: x.reveal_order)
            if r.annotation.strip()
        )


# Fraction of the audio spent drawing; the rest holds the finished frame so
# the drawing always completes with a comfortable margin.
DRAW_BUDGET = 0.75
# How much of each region's slot is set by its narration share vs its ink
# share. Character count is a rough pacing estimate; pauses and variations
# in speaking rate are not measured.
NARRATION_WEIGHT = 0.7


def build_narration_weighted_plan(
    region_plan: SnippetRegionPlan, audio_duration: float,
) -> list[dict] | None:
    """Turn a region plan into animator windows paced by narration.

    With measured `beat_windows`, each region draws when its beat is spoken.
    Otherwise the total drawing spans DRAW_BUDGET of the audio, and within
    that budget each region's slot is proportional to a blend of its
    annotation's character share and its box-area share; that fallback does
    not analyze or align speech.
    """
    regions = sorted(region_plan.regions, key=lambda r: r.reveal_order)
    regions = [r for r in regions if r.box is not None]
    if not regions or audio_duration <= 0:
        return None
    if region_plan.beat_windows:
        return build_beat_aligned_plan(regions, region_plan.beat_windows)

    char_counts = [len((r.annotation or "").strip()) for r in regions]
    total_chars = sum(char_counts)
    areas = [
        max((r.box.xmax - r.box.xmin) * (r.box.ymax - r.box.ymin), 1)
        for r in regions
    ]
    total_area = sum(areas)

    shares = []
    for chars, area in zip(char_counts, areas):
        char_share = chars / total_chars if total_chars else 0.0
        area_share = area / total_area
        if total_chars:
            shares.append(NARRATION_WEIGHT * char_share + (1 - NARRATION_WEIGHT) * area_share)
        else:
            shares.append(area_share)
    total_share = sum(shares) or 1.0

    budget = DRAW_BUDGET * audio_duration
    entries = []
    t = 0.0
    for region, share in zip(regions, shares):
        duration = budget * share / total_share
        entries.append({
            "boxes": [region.box.model_dump()],
            "start": round(t, 3),
            "end": round(t + duration, 3),
        })
        t += duration
    return entries


def build_beat_aligned_plan(
    regions: List[Region], beat_windows: List[List[float]],
) -> list[dict]:
    """One animator window per narration beat, holding that beat's regions.

    Regions start drawing when their sentence starts; the animator draws at a
    natural pace and then holds until the next beat. A region without a valid
    beat joins the last beat so nothing is skipped.
    """
    by_beat: list[list[Region]] = [[] for _ in beat_windows]
    for region in regions:
        beat = region.beat if region.beat and 1 <= region.beat <= len(beat_windows) else len(beat_windows)
        by_beat[beat - 1].append(region)
    return [
        {
            "boxes": [region.box.model_dump() for region in beat_regions],
            "start": round(float(start), 3),
            "end": round(float(end), 3),
        }
        for (start, end), beat_regions in zip(beat_windows, by_beat)
        if beat_regions
    ]
