"""
Whiteboard animation engine.

Turns a whiteboard-style image into a per-pixel reveal-time map and encodes
it as a hand-drawing animation. The pipeline is:

    detect components (CRAFT text + strokes/fills)
        -> order/group them like a hand would draw
        -> schedule each onto the timeline
        -> trace per-pixel reveal times (skeleton strokes, contour outlines,
           sweep/brush fills)
        -> stream frames to ffmpeg

Split across focused modules:
    craft_detector.py      CRAFT text detection (ONNX Runtime, lazy-loaded)
    component_ordering.py  spatial grouping / reading order / box assignment
    skeleton_paths.py      skeleton graph tracing for sequential strokes
    fill_painters.py       reveal-time painters (sweeps, brushes, contours)
    video_encoding.py      timing map -> MP4 via ffmpeg

This module keeps the orchestrating Animator class:
component detection, semantic scheduling, and trace dispatch.
"""

import logging
import time
from collections import defaultdict

import cv2
import numpy as np
from scipy import ndimage
from scipy.ndimage import distance_transform_edt
from skimage.morphology import skeletonize

from .craft_detector import CRAFTDetector, CRAFT_MODEL_PATH
from .component_ordering import (
    assign_components_to_boxes,
    attach_trailing_dots,
    build_spatial_groups,
    order_text_components,
    sort_components_layered,
    sort_components_reading_order,
)
from .fill_painters import (
    brush_strokes_timing,
    contour_timing,
    legacy_sweep_timing,
    simple_timing,
)
from .skeleton_paths import (
    bfs_skeleton,
    build_line_art_strokes,
    extract_skeleton_paths,
    skeleton_degree,
    stroke_progress,
)
from .regions import ensure_pixel_box
from .video_encoding import encode_blank_video, encode_timing_video

logger = logging.getLogger(__name__)

MAX_DIM = 1280


class Animator:

    def __init__(
            self,
            fade_duration: float = 0.12,
            fill_depth_threshold: float = 12.0,
            min_fill_area: int = 200,
            outline_time_fraction: float = 0.35,
            fill_perimeter_area_threshold: float = 0.15,
            # CRAFT settings
            craft_model_path: str = CRAFT_MODEL_PATH,
            craft_text_threshold: float = 0.4,
            craft_link_threshold: float = 0.3,
            craft_low_text: float = 0.25,
            # Text block merging
            word_gap_factor: float = 2.0,
            max_line_gap_factor: float = 1.0,
            min_word_gap_px: int = 8,
            max_line_gap_px: int = 25,
            # Fill detection & animation tuning
            large_fill_area: int = 3000,
            large_fill_depth_factor: float = 0.5,
            large_fill_solidity_min: float = 0.25,
            fill_angle: float = -30.0,
            fill_angle_variance: float = 7.0,
            fill_brush_width: float = 34.0,
            fill_duration_scale: float = 1.00,
            max_fill_duration: float = 3.0,
            brush_fill_min_probability: float = 0.10,
            brush_fill_max_probability: float = 0.90,
            brush_fill_curve_center: float = 0.7,
            brush_fill_curve_steepness: float = 8.0,
            # S-curve sizing window — independent of fill detection thresholds.
            # Shapes at or below `min_area` map to size_progress=0 (legacy floor),
            # shapes at or above `max_area` map to size_progress=1 (brush ceiling).
            # With curve_center=0.7 the 50/50 crossover lands at min + 0.7*(max-min)
            # = 21600 px² (~147×147) under the defaults below — so only genuinely
            # large fills tip toward the brush sweep.
            brush_fill_curve_min_area: int = 2000,
            brush_fill_curve_max_area: int = 30000,
            legacy_fill_angle: float = 30.0,
            # Sequential stroke tracing for multi-branch line art. Any
            # non-text stroke whose skeleton branches (an X, a plus, an
            # arrow with its head, grids, wheels) is decomposed into paths
            # drawn one after another like a hand would, instead of BFS
            # growing every branch at once.
            dense_line_art_min_area: int = 500,
            dense_line_art_min_skeleton: int = 60,
            dense_line_art_min_junctions: int = 1,
            dense_line_art_min_endpoints: int = 4,
            # Multi-color fill splitting
            multicolor_max_colors: int = 2,
            multicolor_min_cluster_fraction: float = 0.10,
    ):
        self.fade_duration = fade_duration
        self.fill_depth_threshold = fill_depth_threshold
        self.min_fill_area = min_fill_area
        self.outline_fraction = outline_time_fraction
        self.fill_perimeter_area_threshold = fill_perimeter_area_threshold
        self.word_gap_factor = word_gap_factor
        self.max_line_gap_factor = max_line_gap_factor
        self.min_word_gap_px = min_word_gap_px
        self.max_line_gap_px = max_line_gap_px

        self.large_fill_area = large_fill_area
        self.large_fill_depth_factor = large_fill_depth_factor
        self.large_fill_solidity_min = large_fill_solidity_min

        self.fill_angle = fill_angle
        self.fill_angle_variance = fill_angle_variance
        self.fill_brush_width = fill_brush_width
        self.fill_duration_scale = fill_duration_scale
        self.max_fill_duration = max_fill_duration
        self.brush_fill_min_probability = brush_fill_min_probability
        self.brush_fill_max_probability = brush_fill_max_probability
        self.brush_fill_curve_center = brush_fill_curve_center
        self.brush_fill_curve_steepness = brush_fill_curve_steepness
        self.brush_fill_curve_min_area = int(brush_fill_curve_min_area)
        self.brush_fill_curve_max_area = int(brush_fill_curve_max_area)
        self.legacy_fill_angle = legacy_fill_angle

        self.dense_line_art_min_area = dense_line_art_min_area
        self.dense_line_art_min_skeleton = dense_line_art_min_skeleton
        self.dense_line_art_min_junctions = dense_line_art_min_junctions
        self.dense_line_art_min_endpoints = dense_line_art_min_endpoints

        self.multicolor_max_colors = max(1, int(multicolor_max_colors))
        self.multicolor_min_cluster_fraction = float(multicolor_min_cluster_fraction)

        self._craft = CRAFTDetector(
            model_path=craft_model_path,
            text_threshold=craft_text_threshold,
            link_threshold=craft_link_threshold,
            low_text=craft_low_text,
        )

    # ==============================================================
    # Aliases into the extracted modules — kept as (static)methods so
    # subclasses can override them and existing self._x() call sites,
    # including the tests', keep working.
    # ==============================================================

    _sort_components_layered = staticmethod(sort_components_layered)
    _sort_components_reading_order = staticmethod(sort_components_reading_order)
    _attach_trailing_dots = staticmethod(attach_trailing_dots)
    _build_spatial_groups = staticmethod(build_spatial_groups)
    _order_text_components = staticmethod(order_text_components)

    _simple_timing = staticmethod(simple_timing)
    _contour_timing = staticmethod(contour_timing)

    _bfs_skeleton = staticmethod(bfs_skeleton)
    _skeleton_degree = staticmethod(skeleton_degree)
    _extract_skeleton_paths = staticmethod(extract_skeleton_paths)
    _build_line_art_strokes = staticmethod(build_line_art_strokes)
    _stroke_progress = staticmethod(stroke_progress)

    def fill_legacy_sweep_timing(self, interior, start, dur, **_):
        return legacy_sweep_timing(interior, start, dur, angle=self.legacy_fill_angle)

    def fill_strokes_timing(self, interior, start, dur, **_):
        return brush_strokes_timing(
            interior, start, dur,
            fill_angle=self.fill_angle,
            angle_variance=self.fill_angle_variance,
            brush_width=self.fill_brush_width,
        )

    # ==============================================================
    # Public API
    # ==============================================================

    @staticmethod
    def downscale(img_array: np.ndarray) -> np.ndarray:
        h, w = img_array.shape[:2]
        if max(h, w) <= MAX_DIM:
            return img_array
        scale = MAX_DIM / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img_array, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def schedule_components(
            self, components: list, draw_duration: float, start: float = 0.0,
    ) -> list:
        """Sequential schedule: list of (comp, start_time, duration)."""
        _weight = lambda c: np.sqrt(c["area"])
        total_weight = sum(_weight(c) for c in components)
        schedule = []
        t = start
        for comp in components:
            dur = max(draw_duration * _weight(comp) / max(total_weight, 1), 0.05)
            if comp["is_fill"]:
                dur = min(dur * self.fill_duration_scale, self.max_fill_duration)
            schedule.append((comp, t, dur))
            t += dur
        return schedule

    def schedule_elements(
            self, components: list, element_plan: list, image_shape: tuple,
    ) -> list:
        """Schedule each group of components across its narration window.

        element_plan entries: {"boxes": [{ymin,xmin,ymax,xmax} normalized
        0-1000, ...], "start": float, "end": float} in order. Windows come
        from transcription and are contiguous, so each group's drawing is
        stretched over exactly the time its narration takes.
        """
        h, w = image_shape
        flat_boxes_px = []   # every item box across all elements
        box_owner = []       # element index owning each flat box
        for element_index, entry in enumerate(element_plan):
            for box in entry.get("boxes") or []:
                flat_boxes_px.append(ensure_pixel_box([
                    int(box["xmin"] / 1000 * w),
                    int(box["ymin"] / 1000 * h),
                    int(box["xmax"] / 1000 * w),
                    int(box["ymax"] / 1000 * h),
                ], w, h))
                box_owner.append(element_index)

        # Structural components that span items of several elements (chart
        # frames, dividers, long connectors, enclosures) belong to the
        # EARLIEST element they cover — containers are drawn before their
        # contents. Spanning multiple items of the SAME element is normal
        # and does not count.
        def box_coverage(comp, box):
            x1, y1, x2, y2 = box
            ix = max(0, min(comp["right"], x2) - max(comp["left"], x1))
            iy = max(0, min(comp["bottom"], y2) - max(comp["top"], y1))
            return (ix * iy) / max((x2 - x1) * (y2 - y1), 1)

        spanning = []
        rest = []
        for comp in components:
            covered_elements = {
                box_owner[i] for i, box in enumerate(flat_boxes_px)
                if box_coverage(comp, box) >= 0.6
            }
            if len(covered_elements) >= 2:
                spanning.append((comp, min(covered_elements)))
            else:
                rest.append(comp)

        flat_assigned, unmatched = assign_components_to_boxes(rest, flat_boxes_px)

        spanning_by_element = [[] for _ in element_plan]
        for comp, element_index in spanning:
            spanning_by_element[element_index].append(comp)

        # A semantic object is a parent mask plus ordered child masks. Pixel
        # connectivity only proposes children: the region box decides which
        # disconnected pieces belong to one visual action.
        per_element = [[] for _ in element_plan]
        for element_index in range(len(element_plan)):
            objects = []
            if spanning_by_element[element_index]:
                for group in self._build_spatial_groups(
                        spanning_by_element[element_index]
                ):
                    objects.append(self.make_semantic_object(group["items"]))
            for box_index, owner in enumerate(box_owner):
                if owner == element_index:
                    item = self.make_semantic_object(flat_assigned[box_index])
                    if item is not None:
                        objects.append(item)
            per_element[element_index] = objects
        if unmatched:
            # Nothing may be skipped. Keep unrelated leftovers in separate
            # spatial parent masks so they cannot interleave.
            for group in self._build_spatial_groups(unmatched):
                item = self.make_semantic_object(group["items"])
                if item is not None:
                    per_element[-1].append(item)

        counts = [len(objects) for objects in per_element]
        logger.info(
            "semantic objects per element: %s (item boxes=%d, spanning=%d, unmatched=%d)",
            counts, len(flat_boxes_px), len(spanning), len(unmatched),
        )

        schedule = []
        for entry, objects in zip(element_plan, per_element):
            if not objects:
                continue
            start = float(entry["start"])
            end = max(float(entry["end"]), start + 0.05)
            for obj, obj_start, obj_duration in self.schedule_semantic_objects(
                    objects, start, end
            ):
                schedule.extend(
                    self.schedule_components_fitted(
                        obj["children"], obj_duration, start=obj_start,
                    )
                )
        return schedule

    @staticmethod
    def schedule_components_fitted(
            components: list, duration: float, start: float = 0.0,
    ) -> list:
        """Fit every child mask inside its semantic parent's exact budget."""
        if not components:
            return []
        weights = [np.sqrt(max(comp["area"], 1)) for comp in components]
        total_weight = sum(weights) or 1.0
        schedule = []
        cursor = start
        for comp, weight in zip(components, weights):
            child_duration = duration * weight / total_weight
            schedule.append((comp, cursor, child_duration))
            cursor += child_duration
        return schedule

    def make_semantic_object(self, items: list) -> dict | None:
        """Create one parent mask whose children must render contiguously."""
        ordered = self.order_item_components(items)
        if not ordered:
            return None
        mask = np.zeros_like(ordered[0]["mask"], dtype=bool)
        for comp in ordered:
            mask |= comp["mask"]
        return {
            "mask": mask,
            "children": ordered,
            "area": int(mask.sum()),
        }

    @staticmethod
    def schedule_semantic_objects(
            objects: list, start: float, end: float,
    ) -> list:
        """Use natural action lengths, then hold instead of stretching ink."""
        if not objects:
            return []

        durations = []
        for obj in objects:
            child_count = len(obj["children"])
            natural = 0.28 + np.sqrt(max(obj["area"], 1)) / 190.0
            natural += min(max(child_count - 1, 0) * 0.07, 0.35)
            durations.append(float(np.clip(natural, 0.3, 1.6)))

        window = max(end - start, 0.05)
        gap = 0.12 if len(objects) > 1 else 0.0
        required = sum(durations) + gap * (len(objects) - 1)
        if required > window:
            available = max(window - gap * (len(objects) - 1), window * 0.8)
            scale = available / max(sum(durations), 1e-6)
            durations = [max(duration * scale, 0.08) for duration in durations]
            gap = max((window - sum(durations)) / max(len(objects) - 1, 1), 0.0)

        schedule = []
        cursor = start
        for obj, duration in zip(objects, durations):
            schedule.append((obj, cursor, duration))
            cursor += duration + gap
        return schedule

    def order_item_components(self, items: list) -> list:
        """Order one item's components the way a hand draws: the object's
        strokes and fills first, its text last."""
        if not items:
            return []
        overlays = [c for c in items if c.get("_is_overlay")]
        base = [c for c in items if not c.get("is_text") and not c.get("_is_overlay")]
        text = [c for c in items if c.get("is_text") and not c.get("_is_overlay")]
        ordered = self._sort_components_reading_order(base) if base else []
        if text:
            ordered.extend(self._sort_components_reading_order(text))
        if overlays:
            ordered.extend(self._sort_components_reading_order(overlays))
        return self._attach_trailing_dots(ordered)

    def render_to_file(
            self,
            img_array: np.ndarray,
            draw_duration: float,
            total_duration: float,
            output_path: str,
            fps: int = 24,
            bitrate: str = "1500k",
            preset: str = "veryfast",
            element_plan: list | None = None,
    ):
        t0 = time.monotonic()
        img_array = self.enforce_white_bg(img_array)
        img_array = self.downscale(img_array)
        components = self.find_components(img_array)
        t1 = time.monotonic()
        logger.info("component detection: %.2fs", t1 - t0)

        h, w = img_array.shape[:2]
        out_h, out_w = h + (h % 2), w + (w % 2)

        if not components:
            encode_blank_video(out_w, out_h, total_duration, output_path, fps, bitrate, preset)
            return

        n_fill = sum(1 for c in components if c["is_fill"])
        n_text = sum(1 for c in components if c.get("is_text"))
        n_stroke = len(components) - n_fill
        logger.info(
            "%d components (%d stroke [%d text], %d fill)",
            len(components), n_stroke, n_text, n_fill,
        )

        has_boxes = element_plan and any(e.get("boxes") for e in element_plan)
        if has_boxes:
            schedule = self.schedule_elements(components, element_plan, (h, w))
        else:
            components = self._sort_components_layered(components)
            schedule = self.schedule_components(components, draw_duration)

        scheduled_ids = {id(comp) for comp, _start, _duration in schedule}
        unscheduled = [comp for comp in components if id(comp) not in scheduled_ids]
        if unscheduled:
            boxes = [
                (c["left"], c["top"], c["right"], c["bottom"])
                for c in unscheduled[:8]
            ]
            raise RuntimeError(
                f"mask scheduler omitted {len(unscheduled)} component(s): {boxes}"
            )
        if has_boxes and schedule:
            plan_end = max(float(entry["end"]) for entry in element_plan)
            schedule_end = max(start + duration for _comp, start, duration in schedule)
            if schedule_end > plan_end + 1e-3:
                raise RuntimeError(
                    f"mask schedule exceeds cue window: {schedule_end:.3f}s > {plan_end:.3f}s"
                )

        timing = np.full((h, w), np.inf, dtype=np.float32)
        for comp, comp_start, dur in schedule:
            ct = self.trace_component(comp, comp_start, dur)
            # Verify and merge on the bbox crop; the mask is empty outside it.
            sl = (slice(comp["top"], comp["bottom"] + 1),
                  slice(comp["left"], comp["right"] + 1))
            mask_crop = comp["mask"][sl]
            ct_crop = ct[sl]
            missing_component_ink = mask_crop & ~np.isfinite(ct_crop)
            if missing_component_ink.any():
                raise RuntimeError(
                    "component trace omitted "
                    f"{int(missing_component_ink.sum())} pixels in "
                    f"({comp['left']},{comp['top']},{comp['right']},{comp['bottom']})"
                )
            timing[sl][mask_crop] = ct_crop[mask_crop]

        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        missing_ink = (gray < 240) & ~np.isfinite(timing)
        if missing_ink.any():
            raise RuntimeError(
                f"mask timing omitted {int(missing_ink.sum())} source-ink pixels"
            )

        draw_end = max((s + d for _, s, d in schedule), default=0.0)
        del components, schedule
        fade_dur = self.fade_duration

        t2 = time.monotonic()
        logger.info("timing computation: %.2fs", t2 - t1)

        encode_timing_video(
            img_array, timing, draw_end, total_duration, fade_dur,
            output_path, fps, bitrate, preset,
        )

    # ==============================================================
    # Text detection via CRAFT
    # ==============================================================

    def detect_text_regions(self, img_rgb: np.ndarray, content: np.ndarray) -> np.ndarray:
        try:
            craft_mask = self._craft.detect(img_rgb)
        except (FileNotFoundError, ImportError) as e:
            logger.warning("CRAFT unavailable (%s), continuing without text detection", e)
            return np.zeros_like(content)

        kern = np.ones((3, 3), np.uint8)
        craft_dilated = cv2.dilate(craft_mask.astype(np.uint8), kern, iterations=1)
        return (craft_dilated > 0) & content

    # ==============================================================
    # Component detection
    # ==============================================================

    def find_components(self, img_array: np.ndarray) -> list:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        content = gray < 240
        if not content.any():
            return []

        text_mask = self.detect_text_regions(img_array, content)
        # Stashed for post-detection refinement passes (e.g. color splitting
        # deciding which ink cluster keeps a component's text role).
        self._last_text_mask = text_mask

        labeled_tight, n_tight = ndimage.label(content.astype(np.uint8))

        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(content.astype(np.uint8), kernel, iterations=1)

        # Vectorized use_tight: per-label area & text-overlap via bincount,
        # then fan out the boolean back to image space in one shot.
        flat_tight = labeled_tight.ravel()
        area_per_label = np.bincount(flat_tight, minlength=n_tight + 1)
        text_overlap_per_label = np.bincount(
            flat_tight,
            weights=text_mask.ravel().astype(np.float32),
            minlength=n_tight + 1,
        )
        with np.errstate(invalid="ignore"):
            text_ratio = text_overlap_per_label / np.maximum(area_per_label, 1)
        use_label = (area_per_label >= 10) & (text_ratio > 0.3)
        use_label[0] = False
        use_tight = use_label[labeled_tight]

        text_content = content.astype(np.uint8).copy()
        text_content[~use_tight] = 0
        labeled_text, n_text = ndimage.label(text_content)

        non_text_content = dilated.copy()
        non_text_content[use_tight] = 0
        labeled_non_text, n_non_text = ndimage.label(non_text_content)

        components = []
        shape = content.shape

        text_objects = ndimage.find_objects(labeled_text)
        for i, sl in enumerate(text_objects, 1):
            if sl is None:
                continue
            mask_local = labeled_text[sl] == i
            area = int(mask_local.sum())
            if area < 8:
                continue
            full_mask = np.zeros(shape, dtype=bool)
            full_mask[sl] = mask_local
            comp = self.build_component(full_mask, area, is_text_override=True)
            if comp:
                components.append(comp)

        non_text_objects = ndimage.find_objects(labeled_non_text)
        for i, sl in enumerate(non_text_objects, 1):
            if sl is None:
                continue
            region_local = labeled_non_text[sl] == i
            mask_local = content[sl] & region_local & ~use_tight[sl]
            area = int(mask_local.sum())
            if area < 10:
                continue

            text_overlap = float((mask_local & text_mask[sl]).sum()) / max(area, 1)
            if text_overlap > 0.4:
                full_mask = np.zeros(shape, dtype=bool)
                full_mask[sl] = mask_local
                comp = self.build_component(full_mask, area, is_text_override=True)
                if comp:
                    components.append(comp)
                continue

            full_mask = np.zeros(shape, dtype=bool)
            full_mask[sl] = mask_local
            split = self.build_connected_components(full_mask, min_area=10)
            if len(split) > 1:
                group = self.build_component_group(split, is_text=False)
                if group:
                    components.append(group)
            elif split:
                components.append(split[0])

        if self.multicolor_max_colors >= 2:
            components = [
                (
                    self.split_multicolor_fill(c, img_array)
                    if c.get("is_fill") and not c.get("_sub_components")
                    else None
                ) or c
                for c in components
            ]

        components = self.split_text_color_overlays(components, img_array)
        components = self.merge_text_blocks(components)
        covered = np.zeros_like(content, dtype=bool)
        for comp in components:
            covered |= comp["mask"]
        residual = content & ~covered
        if residual.any():
            residual_parts = self.build_connected_components(
                residual, min_area=1,
            )
            for part in residual_parts:
                part["_is_residual"] = True
            components.extend(residual_parts)
        return components

    def split_text_color_overlays(
            self, components: list, img_array: np.ndarray,
    ) -> list:
        """Separate colored ink touching neutral text into a later layer.

        This handles the important raster ambiguity directly: a red cross-out
        can be pixel-connected to a black word while still being a different
        drawing action. The two masks are disjoint and their union exactly
        preserves the source component.
        """
        result = []
        for comp in components:
            if not comp.get("is_text"):
                result.append(comp)
                continue

            mask = comp["mask"]
            # Analyze pixels on the bbox crop — full-frame scans per text
            # component dominated detection time on busy images.
            sl = (slice(comp["top"], comp["bottom"] + 1),
                  slice(comp["left"], comp["right"] + 1))
            mask_crop = mask[sl]
            ys, xs = np.where(mask_crop)
            if len(ys) < 32:
                result.append(comp)
                continue

            pixels = img_array[sl][ys, xs].astype(np.int16)
            chroma = pixels.max(axis=1) - pixels.min(axis=1)
            colored_pixels = chroma >= 36
            colored_count = int(colored_pixels.sum())
            neutral_count = len(ys) - colored_count
            min_color = max(24, int(len(ys) * 0.035))
            min_neutral = max(16, int(len(ys) * 0.08))
            if colored_count < min_color or neutral_count < min_neutral:
                result.append(comp)
                continue

            color_crop = np.zeros_like(mask_crop)
            color_crop[ys[colored_pixels], xs[colored_pixels]] = True
            color_mask = np.zeros_like(mask)
            color_mask[sl] = color_crop
            neutral_mask = np.zeros_like(mask)
            neutral_mask[sl] = mask_crop & ~color_crop

            neutral_parts = self.build_connected_components(
                neutral_mask, min_area=1, is_text_override=True,
            )
            color_parts = self.build_connected_components(color_mask, min_area=1)
            if not neutral_parts or not color_parts:
                result.append(comp)
                continue

            result.extend(neutral_parts)
            # Keep disconnected colored marks independent. A red cross-out
            # and colored gauge arcs may originate in one oversized CRAFT
            # text mask, but their spatial boxes belong to different objects.
            for overlay in color_parts:
                overlay["_is_overlay"] = True
                result.append(overlay)
        return result

    def split_multicolor_fill(
            self,
            comp: dict,
            img_array: np.ndarray,
    ) -> dict | None:
        """Split a fill into per-color sub-fills (≤K colors).

        K-means clusters on the eroded interior so anti-aliased edge pixels
        don't pull the centroids; all fill pixels are then labeled by nearest
        centroid for masking. Pixel colors in img_array are NOT modified —
        the renderer reads originals so soft fill→background edges and color
        seams stay smooth. Returns None if the fill is effectively
        monochromatic."""
        max_colors = self.multicolor_max_colors
        if max_colors < 2:
            return None

        mask = comp["mask"]
        ys, xs = np.where(mask)
        n = len(ys)
        if n < max_colors * 8:
            return None

        # Cluster on the deep interior to keep centers off anti-aliased edges.
        kernel = np.ones((3, 3), np.uint8)
        inner_mask = cv2.erode(
            mask.astype(np.uint8), kernel, iterations=2,
        ).astype(bool)
        inner_pixels = img_array[inner_mask].astype(np.float32)
        if len(inner_pixels) < max_colors * 4:
            inner_pixels = img_array[ys, xs].astype(np.float32)

        all_pixels = img_array[ys, xs].astype(np.float32)
        k = min(max_colors, len(inner_pixels))
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 8, 1.0)
        try:
            _, _, centers = cv2.kmeans(
                inner_pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS,
            )
        except cv2.error:
            return None

        # Assign every fill pixel (including edges) to its nearest clean center.
        d = np.linalg.norm(
            all_pixels[:, None, :] - centers[None, :, :], axis=2,
        )
        labels = np.argmin(d, axis=1).astype(np.int32)

        counts = np.bincount(labels, minlength=k)
        min_count = max(int(n * self.multicolor_min_cluster_fraction), 1)
        keep = np.where(counts >= min_count)[0]
        if len(keep) <= 1:
            return None

        if len(keep) < k:
            kept_centers = centers[keep]
            d = np.linalg.norm(
                all_pixels[:, None, :] - kept_centers[None, :, :], axis=2,
            )
            labels = np.argmin(d, axis=1).astype(np.int32)
            centers = kept_centers
            k = len(keep)

        centers_u8 = np.clip(centers, 0, 255).astype(np.uint8)

        shape = mask.shape
        subs = []
        for ci in range(k):
            sel = labels == ci
            if not sel.any():
                continue
            sub_mask = np.zeros(shape, dtype=bool)
            sub_mask[ys[sel], xs[sel]] = True
            sub_area = int(sel.sum())
            sub = self.build_component(sub_mask, sub_area, force_fill=True)
            if sub:
                color = centers_u8[ci].astype(np.float32)
                sub["_fill_color"] = color
                sub["_black_distance"] = float(np.linalg.norm(color))
                subs.append(sub)

        if len(subs) <= 1:
            return None

        # Closest-to-black first; larger area breaks ties.
        subs.sort(key=lambda s: (s["_black_distance"], -s["area"]))
        group = self.build_component_group(subs, is_text=False)
        if group is None:
            return None
        group["is_fill"] = True
        group["_multicolor_fill"] = True
        return group

    def build_connected_components(
            self, mask: np.ndarray, min_area: int = 1, is_text_override: bool = False
    ) -> list:
        labeled, n_labels = ndimage.label(mask.astype(np.uint8))
        if n_labels == 0:
            return []

        objects = ndimage.find_objects(labeled)
        shape = mask.shape
        components = []
        for i, sl in enumerate(objects, 1):
            if sl is None:
                continue
            sub_local = (labeled[sl] == i) & mask[sl]
            area = int(sub_local.sum())
            if area < min_area:
                continue
            sub_mask = np.zeros(shape, dtype=bool)
            sub_mask[sl] = sub_local
            comp = self.build_component(
                sub_mask, area, is_text_override=is_text_override
            )
            if comp:
                components.append(comp)
        return components

    def build_component(
            self, mask: np.ndarray, area: int, is_text_override: bool = False,
            force_fill: bool = False,
    ) -> dict | None:
        # Axis reductions beat np.where here: bbox only needs row/col extents,
        # not every pixel coordinate materialized.
        rows = np.flatnonzero(mask.any(axis=1))
        cols = np.flatnonzero(mask.any(axis=0))
        top, bottom = int(rows[0]), int(rows[-1])
        left, right = int(cols[0]), int(cols[-1])

        crop = mask[top:bottom + 1, left:right + 1]
        crop_u8 = crop.astype(np.uint8)

        if is_text_override:
            close_k = np.ones((3, 3), np.uint8)
            solid_crop = cv2.morphologyEx(crop_u8, cv2.MORPH_CLOSE, close_k, iterations=1)
        else:
            close_k = np.ones((9, 9), np.uint8)
            solid_crop = cv2.morphologyEx(crop_u8, cv2.MORPH_CLOSE, close_k, iterations=2)

        h, w = mask.shape
        solid_mask = np.zeros((h, w), dtype=bool)
        solid_mask[top:bottom + 1, left:right + 1] = solid_crop > 0

        # A tight component crop can contain no background pixels (for
        # example, a straight marker capsule filling its bbox). EDT then
        # measures toward an arbitrary array edge and reports a depth close
        # to the component's length instead of half its stroke width. Supply
        # an explicit background border so thickness is measured correctly.
        padded_crop = np.pad(crop, 1, mode="constant", constant_values=False)
        dt = distance_transform_edt(padded_crop)[1:-1, 1:-1]
        max_depth = float(dt.max())

        cnts, _ = cv2.findContours(crop_u8, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        perim = sum(cv2.arcLength(c, True) for c in cnts) if cnts else 0.0
        pa_ratio = perim / max(area, 1)

        bbox_area = max((bottom - top + 1) * (right - left + 1), 1)
        solidity = area / bbox_area

        if force_fill:
            is_fill = True
        else:
            is_fill = not is_text_override and area >= self.min_fill_area and (
                    (max_depth > self.fill_depth_threshold
                     and pa_ratio < self.fill_perimeter_area_threshold)
                    or (area >= self.large_fill_area
                        and max_depth > self.fill_depth_threshold * self.large_fill_depth_factor
                        and solidity > self.large_fill_solidity_min)
            )

        return {
            "mask": mask,
            "skeleton": None,  # deferred to trace_stroke (lazy)
            "skel_len": area if is_fill else 0,
            "skel_start": (top, left),
            "max_depth": max_depth,
            "is_fill": is_fill,
            "is_text": is_text_override,
            "solid_mask": solid_mask,
            "top": top,
            "bottom": bottom,
            "left": left,
            "right": right,
            "area": area,
        }

    def build_component_group(self, sub_components: list, is_text: bool) -> dict | None:
        if not sub_components:
            return None
        if len(sub_components) == 1:
            return sub_components[0]

        ref = sub_components[0]
        h, w = ref["mask"].shape
        combined = np.zeros((h, w), dtype=bool)
        solid = np.zeros((h, w), dtype=bool)

        top, bottom = h, 0
        left, right = w, 0
        max_depth = 0.0

        for sub in sub_components:
            combined |= sub["mask"]
            solid |= sub["solid_mask"]
            top = min(top, sub["top"])
            bottom = max(bottom, sub["bottom"])
            left = min(left, sub["left"])
            right = max(right, sub["right"])
            max_depth = max(max_depth, sub["max_depth"])

        area = int(combined.sum())
        return {
            "mask": combined,
            "skeleton": None,
            "skel_len": max(area, 1),
            "skel_start": (top, left),
            "max_depth": max_depth,
            "is_fill": False,
            "is_text": is_text,
            "solid_mask": solid,
            "top": top,
            "bottom": bottom,
            "left": left,
            "right": right,
            "area": area,
            "_sub_components": sub_components,
        }

    # ==============================================================
    # Text block merging
    # ==============================================================

    def merge_text_blocks(self, components: list) -> list:
        text = [c for c in components if c.get("is_text")]
        other = [c for c in components if not c.get("is_text")]

        if len(text) <= 1:
            return components

        parent = list(range(len(text)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(len(text)):
            ci = text[i]
            hi = ci["bottom"] - ci["top"]
            for j in range(i + 1, len(text)):
                cj = text[j]
                hj = cj["bottom"] - cj["top"]

                yov = min(ci["bottom"], cj["bottom"]) - max(ci["top"], cj["top"])
                if yov > min(hi, hj) * 0.3:
                    xgap = max(ci["left"], cj["left"]) - min(ci["right"], cj["right"])
                    max_gap = min(
                        max(max(hi, hj) * self.word_gap_factor, self.min_word_gap_px),
                        self.max_line_gap_px * 2,
                        )
                    if xgap < max_gap:
                        union(i, j)
                        continue

                xov = min(ci["right"], cj["right"]) - max(ci["left"], cj["left"])
                mw = min(ci["right"] - ci["left"], cj["right"] - cj["left"])
                if xov > mw * 0.3:
                    ygap = max(ci["top"], cj["top"]) - min(ci["bottom"], cj["bottom"])
                    ygap_threshold = min(
                        (hi + hj) / 2 * self.max_line_gap_factor,
                        self.max_line_gap_px,
                        )
                    if 0 <= ygap < ygap_threshold:
                        union(i, j)

        groups = defaultdict(list)
        for i in range(len(text)):
            groups[find(i)].append(i)

        merged = []
        for indices in groups.values():
            if len(indices) == 1:
                merged.append(text[indices[0]])
                continue

            group = self.build_component_group(
                [text[idx] for idx in indices], is_text=True
            )
            if group:
                merged.append(group)

        return other + merged

    # ==============================================================
    # STROKE animation
    # ==============================================================

    def trace_component(self, comp: dict, start: float, dur: float) -> np.ndarray:
        if comp.get("_sub_components"):
            return self.trace_component_group(comp, start, dur)
        if comp["is_fill"]:
            if self.is_marker_stroke(comp):
                marker = dict(comp)
                marker["is_fill"] = False
                return self.trace_stroke(marker, start, dur)
            return self.trace_filled(comp, start, dur)
        return self.trace_stroke(comp, start, dur)

    @staticmethod
    def is_marker_stroke(comp: dict) -> bool:
        """Distinguish a thick pen mark from a genuinely solid shape."""
        width = max(comp["right"] - comp["left"] + 1, 1)
        height = max(comp["bottom"] - comp["top"] + 1, 1)
        bbox_area = width * height
        short_side = min(width, height)
        long_side = max(width, height)
        fill_ratio = comp["area"] / max(bbox_area, 1)
        max_depth = comp.get("max_depth", short_side)
        elongated = (
            long_side >= short_side * 3.5
            and max_depth <= short_side * 0.60
        )
        sparse_branched = (
            fill_ratio <= 0.45
            and max_depth <= long_side * 0.18
        )
        return (
            short_side >= 16
            and (elongated or sparse_branched)
        )

    def trace_stroke(self, comp: dict, start: float, dur: float) -> np.ndarray:
        mask = comp["mask"]
        skeleton = comp["skeleton"]
        skel_start = comp["skel_start"]
        h, w = mask.shape
        timing = np.full((h, w), np.inf, dtype=np.float32)

        top, bottom, left, right = comp["top"], comp["bottom"], comp["left"], comp["right"]
        pad = 2
        ct, cb = max(0, top - pad), min(h, bottom + 1 + pad)
        cl, cr = max(0, left - pad), min(w, right + 1 + pad)

        mask_crop = mask[ct:cb, cl:cr]
        ys_c, xs_c = np.where(mask_crop)
        if len(ys_c) == 0:
            return timing
        if len(ys_c) <= 2:
            timing[ys_c + ct, xs_c + cl] = start
            return timing

        # Lazy skeleton computation
        if skeleton is None and not comp["is_fill"]:
            crop = mask[top:bottom + 1, left:right + 1]
            try:
                skel_crop = skeletonize(crop)
            except Exception:
                skel_crop = np.zeros_like(crop)
            if skel_crop.any():
                skeleton = np.zeros((h, w), dtype=bool)
                skeleton[top:bottom + 1, left:right + 1] = skel_crop
                sy, sx = np.where(skeleton)
                d = (sy - top) ** 2 + (sx - left) ** 2
                b = int(np.argmin(d))
                skel_start = (int(sy[b]), int(sx[b]))

        skel_crop = skeleton[ct:cb, cl:cr] if skeleton is not None else None

        if skel_crop is None or not skel_crop.any():
            return self._simple_timing(mask, skel_start, start, dur)

        degree = self._skeleton_degree(skel_crop)
        endpoints = np.column_stack(np.where(skel_crop & (degree == 1)))
        if len(endpoints):
            # Open marks always start from a real endpoint. The previous
            # bbox-nearest seed often landed on the apex of a V or the hub of
            # a diagram and produced the unmistakable middle-out effect.
            endpoint = min(endpoints, key=lambda point: (int(point[0]), int(point[1])))
            skel_start_c = (int(endpoint[0]), int(endpoint[1]))
        else:
            skel_points = np.column_stack(np.where(skel_crop))
            canonical = min(
                skel_points, key=lambda point: (int(point[0]), int(point[1]))
            )
            skel_start_c = (int(canonical[0]), int(canonical[1]))

            # A simple closed mark needs one front travelling around the
            # contour. BFS would send two fronts in opposite directions.
            if int(degree[skel_crop].max()) <= 2:
                return self._contour_timing(mask, mask, start, dur)

        if self.is_dense_line_art(comp, skel_crop):
            dense_timing = self.trace_dense_line_art(mask_crop, skel_crop, start, dur)
            if dense_timing is not None:
                timing[ys_c + ct, xs_c + cl] = dense_timing[ys_c, xs_c]
                return timing

        skel_dists_c = self._bfs_skeleton(skel_crop, skel_start_c)
        valid = skel_dists_c < np.inf
        if not valid.any():
            return self._simple_timing(mask, skel_start, start, dur)

        max_sd = max(skel_dists_c[valid].max(), 1)
        d2s_c, nearest_c = ndimage.distance_transform_edt(~skel_crop, return_indices=True)
        max_d2s = max(d2s_c[mask_crop].max(), 1)

        nys, nxs = nearest_c[0, ys_c, xs_c], nearest_c[1, ys_c, xs_c]
        if not np.all(valid[nys, nxs]):
            return self._simple_timing(mask, skel_start, start, dur)
        prog = np.clip(
            skel_dists_c[nys, nxs] / max_sd + (d2s_c[ys_c, xs_c] / max_d2s) * 0.02,
            0, 1,
            )
        timing[ys_c + ct, xs_c + cl] = start + prog * dur
        return timing

    def is_dense_line_art(self, comp: dict, skel_crop: np.ndarray) -> bool:
        if comp.get("is_fill"):
            return False

        skel_count = int(skel_crop.sum())
        if skel_count < 4:
            return False

        degree = self._skeleton_degree(skel_crop)
        endpoint_count = int((skel_crop & (degree == 1)).sum())
        junction_mask = skel_crop & (degree >= 3)
        _, junction_count = ndimage.label(junction_mask.astype(np.uint8))

        # BFS reveals every outgoing arm at once after reaching a junction,
        # which creates a pinwheel/starburst. Always reconstruct continuous
        # paths for a genuine junction, including small and text-classified
        # strokes. The area thresholds remain useful for endpoint-heavy line
        # art without an explicitly detected junction.
        if junction_count >= self.dense_line_art_min_junctions:
            return True
        if comp.get("is_text"):
            return False
        if comp["area"] < self.dense_line_art_min_area:
            return False
        if skel_count < self.dense_line_art_min_skeleton:
            return False
        return (
                endpoint_count >= self.dense_line_art_min_endpoints
        )

    def trace_dense_line_art(
            self,
            mask_crop: np.ndarray,
            skel_crop: np.ndarray,
            start: float,
            dur: float,
    ) -> np.ndarray | None:
        paths = self._extract_skeleton_paths(skel_crop)
        if not paths:
            return None

        strokes = self._build_line_art_strokes(paths, skel_crop)
        if not strokes:
            return None

        h, w = mask_crop.shape
        skel_timing = np.full((h, w), np.inf, dtype=np.float32)
        total_weight = sum(max(float(s["weight"]), 1.0) for s in strokes)
        t = start

        for stroke in strokes:
            coords = stroke["coords"]
            if coords.size == 0:
                continue

            sd = dur * max(float(stroke["weight"]), 1.0) / max(total_weight, 1.0)
            ys = coords[:, 0].astype(np.int32)
            xs = coords[:, 1].astype(np.int32)
            progress = self._stroke_progress(stroke, coords)
            times = np.clip(t + progress * sd, start, start + dur).astype(np.float32)
            skel_timing[ys, xs] = np.minimum(skel_timing[ys, xs], times)
            t += sd

        assigned = np.isfinite(skel_timing) & skel_crop
        if not assigned.any():
            return None

        missing = skel_crop & ~assigned
        if missing.any():
            _, near_assigned = ndimage.distance_transform_edt(~assigned, return_indices=True)
            ys_m, xs_m = np.where(missing)
            skel_timing[ys_m, xs_m] = skel_timing[
                near_assigned[0, ys_m, xs_m], near_assigned[1, ys_m, xs_m]
            ]

        timing = np.full((h, w), np.inf, dtype=np.float32)
        ys, xs = np.where(mask_crop)
        if len(ys) == 0:
            return timing

        d2s, nearest = ndimage.distance_transform_edt(~skel_crop, return_indices=True)
        base = skel_timing[nearest[0, ys, xs], nearest[1, ys, xs]]
        if not np.isfinite(base).all():
            return None

        max_d2s = max(float(d2s[ys, xs].max()), 1.0)
        spread = min(dur * 0.025, self.fade_duration * 0.5)
        timing[ys, xs] = np.clip(
            base + (d2s[ys, xs] / max_d2s) * spread,
            start,
            start + dur,
        )
        return timing

    def trace_component_group(self, comp: dict, start: float, dur: float) -> np.ndarray:
        subs = comp.get("_sub_components")
        if not subs or len(subs) <= 1:
            return self.trace_component({k: v for k, v in comp.items() if k != "_sub_components"}, start, dur)

        h, w = comp["mask"].shape
        timing = np.full((h, w), np.inf, dtype=np.float32)

        if comp.get("_multicolor_fill"):
            ordered = list(subs)
            weights = [np.sqrt(s["area"]) for s in ordered]
        elif comp.get("is_text"):
            ordered = self._order_text_components(subs)
            weights = [s["area"] for s in ordered]
        else:
            ordered = self._sort_components_layered(list(subs))
            weights = [np.sqrt(s["area"]) for s in ordered]

        total_a = sum(weights)
        t = start
        for sub, weight in zip(ordered, weights):
            sd = dur * weight / max(total_a, 1)
            st = self.trace_component(sub, t, sd)
            sl = (slice(sub["top"], sub["bottom"] + 1),
                  slice(sub["left"], sub["right"] + 1))
            mask_crop = sub["mask"][sl]
            timing[sl][mask_crop] = st[sl][mask_crop]
            t += sd
        return timing

    # ==============================================================
    # FILL animation
    # ==============================================================

    def trace_filled(self, comp: dict, start: float, dur: float) -> np.ndarray:
        mask = comp["mask"]
        solid = comp["solid_mask"]
        h, w = mask.shape

        kern = np.ones((4, 4), np.uint8)
        eroded = cv2.erode(solid.astype(np.uint8), kern, iterations=4)

        boundary = mask & (solid & (eroded == 0))
        interior = mask & (solid & (eroded > 0))

        if not interior.any():
            return self.trace_stroke(comp, start, dur)

        boundary_pixels = int(np.count_nonzero(boundary))
        interior_pixels = int(np.count_nonzero(interior))
        outline_fraction = min(
            self.outline_fraction,
            boundary_pixels / max(boundary_pixels + interior_pixels, 1),
        )

        ol_dur = dur * outline_fraction
        fi_dur = dur * (1 - outline_fraction)
        fi_start = start + ol_dur

        ol_t = self._contour_timing(boundary, solid, start, ol_dur)
        fi_t = self.mixed_fill_timing(comp, interior, fi_start, fi_dur)

        timing = np.full((h, w), np.inf, dtype=np.float32)
        timing = np.where(boundary, ol_t, timing)
        timing = np.where(interior, fi_t, timing)
        return timing

    def mixed_fill_timing(self, comp: dict, interior, start: float, dur: float) -> np.ndarray:
        """Choose legacy or brush fill deterministically, weighted by object size.

        Probability follows an S-curve in size_progress so small/medium shapes
        almost always get the legacy sweep and only larger shapes cross over to
        the brush fill. The curve's midpoint is `brush_fill_curve_center` and
        its steepness is `brush_fill_curve_steepness`.
        """
        area = max(int(comp.get("area", int(np.count_nonzero(interior)))), 1)
        curve_lo = float(self.brush_fill_curve_min_area)
        curve_hi = float(self.brush_fill_curve_max_area)
        size_span = max(curve_hi - curve_lo, 1.0)
        size_progress = np.clip((area - curve_lo) / size_span, 0.0, 1.0)

        min_prob = float(np.clip(self.brush_fill_min_probability, 0.0, 1.0))
        max_prob = float(np.clip(self.brush_fill_max_probability, 0.0, 1.0))
        if max_prob < min_prob:
            min_prob, max_prob = max_prob, min_prob

        center = float(np.clip(self.brush_fill_curve_center, 0.0, 1.0))
        steepness = max(float(self.brush_fill_curve_steepness), 1e-3)
        # Normalised sigmoid: maps size_progress=0 to ~0 and size_progress=1 to ~1
        # with the inflection point at `center`. Renormalised so the endpoints
        # actually hit 0 and 1 even when `center` is off-centre.
        s_lo = 1.0 / (1.0 + np.exp(steepness * center))
        s_hi = 1.0 / (1.0 + np.exp(-steepness * (1.0 - center)))
        s_raw = 1.0 / (1.0 + np.exp(-steepness * (size_progress - center)))
        s_norm = (s_raw - s_lo) / max(s_hi - s_lo, 1e-9)
        s_norm = float(np.clip(s_norm, 0.0, 1.0))
        brush_probability = min_prob + s_norm * (max_prob - min_prob)

        seed = (
            int(comp.get("top", 0)) * 73856093
            ^ int(comp.get("bottom", 0)) * 19349663
            ^ int(comp.get("left", 0)) * 83492791
            ^ int(comp.get("right", 0)) * 2654435761
            ^ area * 97531
            ^ 0x9E3779B9
        ) & 0xFFFFFFFF
        rng = np.random.RandomState(seed)

        if rng.rand() < brush_probability:
            return self.fill_strokes_timing(interior, start, dur)
        return self.fill_legacy_sweep_timing(interior, start, dur)

    # ==============================================================
    # Shared helpers
    # ==============================================================

    @staticmethod
    def enforce_white_bg(img):
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        r = img.copy()
        r[gray > 240] = [255, 255, 255]
        return r
