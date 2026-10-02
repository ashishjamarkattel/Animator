"""Per-pixel reveal-time painters.

Each function returns a float32 timing map (inf = untouched) assigning every
pixel of a mask a reveal time within [start, start + dur]: simple axis sweeps,
contour tracing for outlines, and the two fill styles (legacy angled sweep and
bristle-textured brush strokes).
"""

import numpy as np
import cv2
from scipy import ndimage


def simple_timing(mask, start_pt, start, dur):
    h, w = mask.shape
    timing = np.full((h, w), np.inf, dtype=np.float32)
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return timing
    x_span = int(xs.max() - xs.min())
    y_span = int(ys.max() - ys.min())
    if x_span >= y_span:
        progress = (xs - xs.min()) / max(x_span, 1)
    else:
        progress = (ys - ys.min()) / max(y_span, 1)
    timing[ys, xs] = start + progress.astype(np.float32) * dur
    return timing


def contour_timing(boundary, full_mask, start, dur):
    full_h, full_w = boundary.shape
    full_timing = np.full((full_h, full_w), np.inf, dtype=np.float32)

    # All work happens on the bbox crop — boundary is a subset of full_mask,
    # so both fit; full-frame contour/EDT passes dominated the fill cost.
    rows = np.flatnonzero(full_mask.any(axis=1))
    if len(rows) == 0:
        return full_timing
    cols = np.flatnonzero(full_mask.any(axis=0))
    sl = (slice(int(rows[0]), int(rows[-1]) + 1),
          slice(int(cols[0]), int(cols[-1]) + 1))
    full_mask = full_mask[sl]
    boundary = boundary[sl]
    h, w = boundary.shape
    timing = np.full((h, w), np.inf, dtype=np.float32)

    contours, _ = cv2.findContours(
        full_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    if not contours:
        ys, xs = np.where(boundary)
        if len(ys) == 0:
            return full_timing
        full_timing[sl] = simple_timing(boundary, (int(ys[0]), int(xs[0])), start, dur)
        return full_timing

    ordered_contours = []
    for contour in sorted(contours, key=len, reverse=True):
        points = contour.reshape(-1, 2)
        if len(points) < 2:
            continue
        # Canonical top-left start. Choose the direction that initially
        # travels right when possible, matching a natural frame stroke.
        start_index = min(
            range(len(points)),
            key=lambda index: (int(points[index, 1]), int(points[index, 0])),
        )
        forward = np.concatenate((points[start_index:], points[:start_index]))
        reverse_points = points[::-1]
        reverse_index = min(
            range(len(reverse_points)),
            key=lambda index: (
                int(reverse_points[index, 1]), int(reverse_points[index, 0]),
            ),
        )
        reverse = np.concatenate(
            (reverse_points[reverse_index:], reverse_points[:reverse_index])
        )
        lookahead = min(8, len(points) - 1)
        points = (
            forward
            if forward[lookahead, 0] >= reverse[lookahead, 0]
            else reverse
        )
        ordered_contours.append(points.reshape(-1, 1, 2))
    if not ordered_contours:
        return full_timing
    all_pts = np.concatenate(ordered_contours, axis=0).reshape(-1, 2)
    n = len(all_pts)
    xc, yc = all_pts[:, 0], all_pts[:, 1]
    v = (yc >= 0) & (yc < h) & (xc >= 0) & (xc < w)
    xv, yv = xc[v], yc[v]
    flat = yv.astype(np.int64) * w + xv.astype(np.int64)
    _, fo = np.unique(flat, return_index=True)
    prog = np.arange(n, dtype=np.float32)[v] / max(n - 1, 1)
    timing[yv[fo], xv[fo]] = start + prog[fo] * dur

    thin = np.zeros((h, w), dtype=bool)
    thin[yv[fo], xv[fo]] = True
    rem = boundary & ~thin
    if rem.any() and thin.any():
        _, near = ndimage.distance_transform_edt(~thin, return_indices=True)
        ys, xs = np.where(rem)
        timing[ys, xs] = timing[near[0, ys, xs], near[1, ys, xs]]

    full_timing[sl] = timing
    return full_timing


def legacy_sweep_timing(interior, start, dur, angle: float = 30.0):
    """Paint interior pixels with the original angled sweep fill."""
    h, w = interior.shape
    timing = np.full((h, w), np.inf, dtype=np.float32)
    ys, xs = np.where(interior)
    if len(ys) == 0:
        return timing

    rng = np.random.RandomState(42)
    yf, xf = ys.astype(np.float32), xs.astype(np.float32)
    y_min, y_max = float(yf.min()), float(yf.max())
    x_min, x_max = float(xf.min()), float(xf.max())
    y_span = max(y_max - y_min, 1.0)
    x_span = max(x_max - x_min, 1.0)

    angle_rad = np.radians(angle)
    dy = np.cos(angle_rad)
    dx = np.sin(angle_rad)

    proj = (yf - y_min) * dy + (xf - x_min) * dx
    proj_min = proj.min()
    proj_span = max(proj.max() - proj_min, 1.0)
    base_progress = (proj - proj_min) / proj_span

    cw = 4.0
    nc = max(int(x_span / cw) + 2, 1)
    ci = np.clip(((xf - x_min) / cw).astype(np.int32), 0, nc - 1)

    cs = rng.uniform(-0.03, 0.03, size=nc).astype(np.float32)
    cs[0] = 0.0
    cspd = np.clip(1.0 + np.cumsum(cs), 0.88, 1.12)
    cspd -= cspd.mean() - 1.0
    pspd = cspd[ci]

    rbh = 6.0
    nrb = max(int(y_span / rbh) + 2, 1)
    ws = rng.uniform(-0.006, 0.006, size=(nrb, nc)).astype(np.float32)
    ws[0, :] = 0.0
    wob = np.clip(np.cumsum(ws, axis=0), -0.04, 0.04)
    wob -= wob.mean(axis=0, keepdims=True)
    rbi = np.clip(((yf - y_min) / rbh).astype(np.int32), 0, nrb - 1)
    pw = wob[rbi, ci] * dur

    pn = rng.uniform(-0.003, 0.003, size=len(ys)).astype(np.float32) * dur
    pt = np.clip(start + base_progress * pspd * dur + pw + pn, start, start + dur)
    timing[ys, xs] = pt
    return timing


def brush_strokes_timing(
        interior, start, dur, *,
        fill_angle: float = -30.0,
        angle_variance: float = 7.0,
        brush_width: float = 34.0,
):
    """Paint interior pixels with one pass of alternating bristle-textured brush strokes."""
    h, w = interior.shape
    timing = np.full((h, w), np.inf, dtype=np.float32)
    ys, xs = np.where(interior)
    if len(ys) == 0:
        return timing

    yf, xf = ys.astype(np.float32), xs.astype(np.float32)
    y_min, y_max = float(yf.min()), float(yf.max())
    x_min, x_max = float(xf.min()), float(xf.max())

    seed = (
        int(y_min) * 73856093
        ^ int(y_max) * 19349663
        ^ int(x_min) * 83492791
        ^ int(x_max) * 2654435761
        ^ len(ys) * 97531
    ) & 0xFFFFFFFF
    rng = np.random.RandomState(seed)

    bbox_w = max(x_max - x_min, 1.0)
    bbox_h = max(y_max - y_min, 1.0)
    aspect_ratio = bbox_w / bbox_h
    if aspect_ratio > 1.15:
        base_angle = 0.0
    elif aspect_ratio < 1.0 / 1.15:
        base_angle = 90.0
    else:
        base_angle = 0.0 if rng.rand() < 0.5 else 90.0

    angle_variance = max(float(angle_variance), 0.0)
    stroke_angle = base_angle + float(fill_angle)
    if angle_variance > 0:
        stroke_angle += float(rng.uniform(-angle_variance, angle_variance))
    angle_rad = np.radians(stroke_angle)
    dx = np.cos(angle_rad)
    dy = np.sin(angle_rad)

    rel_y = yf - y_min
    rel_x = xf - x_min
    along = rel_x * dx + rel_y * dy
    across = rel_y * dx - rel_x * dy

    along_min = float(along.min())
    along_max = float(along.max())
    across_min = float(across.min())
    across_max = float(across.max())
    across_span = max(across_max - across_min, 1.0)
    brush_width = max(float(brush_width), 1.0)

    lane_start = across_min - brush_width * 0.5
    lane_widths = []
    covered = 0.0
    target_span = across_span + brush_width
    while covered < target_span:
        lane_width = brush_width * float(rng.uniform(0.72, 1.38))
        lane_widths.append(lane_width)
        covered += lane_width

    lane_edges = lane_start + np.concatenate(
        ([0.0], np.cumsum(np.array(lane_widths, dtype=np.float32)))
    )
    n_lanes = len(lane_widths)
    lane_idx = np.searchsorted(lane_edges[1:], across, side="right")
    lane_idx = np.clip(lane_idx, 0, n_lanes - 1).astype(np.int32)

    lane_y_min = np.full(n_lanes, np.inf, dtype=np.float32)
    lane_y_max = np.full(n_lanes, -np.inf, dtype=np.float32)
    for lane in range(n_lanes):
        lane_along = along[lane_idx == lane]
        if len(lane_along) == 0:
            continue
        lane_y_min[lane] = lane_along.min()
        lane_y_max[lane] = lane_along.max()

    missing_lanes = ~np.isfinite(lane_y_min)
    lane_y_min[missing_lanes] = along_min
    lane_y_max[missing_lanes] = along_max

    lane_span = np.maximum(lane_y_max[lane_idx] - lane_y_min[lane_idx], 1.0)
    down_progress = (along - lane_y_min[lane_idx]) / lane_span
    up_progress = (lane_y_max[lane_idx] - along) / lane_span
    vertical_progress = np.where((lane_idx % 2) == 0, down_progress, up_progress)
    vertical_progress = np.clip(vertical_progress, 0.0, 1.0)

    lane_left = lane_edges[lane_idx]
    lane_right = lane_edges[lane_idx + 1]
    lane_width_at_pixel = np.maximum(lane_right - lane_left, 1.0)
    local_across = across - lane_left
    local_across_norm = np.clip(local_across / lane_width_at_pixel, 0.0, 1.0)
    edge_distance = np.minimum(local_across, lane_width_at_pixel - local_across)
    edge_proximity = 1.0 - np.clip(
        edge_distance / (lane_width_at_pixel * 0.45),
        0.0,
        1.0,
    )
    brush_taper = np.power(edge_proximity, 1.35) * 0.095

    bristle_width = max(brush_width * 0.11, 2.0)
    bristle_idx = np.floor((across - across_min) / bristle_width).astype(np.int32)
    bristle_idx -= int(bristle_idx.min())
    n_bristles = int(bristle_idx.max()) + 1
    bristle_offsets = rng.uniform(-0.045, 0.04, size=n_bristles).astype(np.float32)
    bristle_texture = bristle_offsets[bristle_idx] * (1.0 - local_across_norm * 0.12)

    grain_along = max(brush_width * 0.42, 5.0)
    grain_across = max(brush_width * 0.16, 3.0)
    grain_y = np.floor((along - along_min) / grain_along).astype(np.int32)
    grain_x = np.floor((across - across_min) / grain_across).astype(np.int32)
    grain_y -= int(grain_y.min())
    grain_x -= int(grain_x.min())
    grain_cols = int(grain_x.max()) + 1
    grain_idx = grain_y * grain_cols + grain_x
    n_grains = int(grain_idx.max()) + 1
    grain_values = rng.uniform(0.0, 1.0, size=n_grains).astype(np.float32)
    grain_lags = rng.uniform(0.035, 0.105, size=n_grains).astype(np.float32)
    dry_brush_lag = np.where(
        grain_values[grain_idx] > 0.88,
        grain_lags[grain_idx] * (1.0 - edge_proximity * 0.45),
        0.0,
    ).astype(np.float32)

    lane_weights = rng.uniform(0.75, 1.45, size=n_lanes).astype(np.float32)
    pause_weights = rng.uniform(0.0, 0.22, size=n_lanes).astype(np.float32)
    pause_weights[0] = 0.0
    lane_units = lane_weights + pause_weights
    total_units = max(float(lane_units.sum()), 1.0)
    lane_starts = np.concatenate(([0.0], np.cumsum(lane_units[:-1]))).astype(np.float32)
    lane_starts = lane_starts / total_units
    lane_durs = lane_weights / total_units
    pause_durs = pause_weights / total_units
    lane_curves = rng.uniform(0.78, 1.35, size=n_lanes).astype(np.float32)

    curved_progress = np.power(vertical_progress, lane_curves[lane_idx])
    stroke_progress = np.clip(
        curved_progress * 0.86 + brush_taper + bristle_texture + dry_brush_lag,
        0.0,
        1.0,
    )
    progress = (
        lane_starts[lane_idx]
        + pause_durs[lane_idx]
        + stroke_progress * lane_durs[lane_idx]
    )
    progress = np.clip(progress, 0.0, 1.0)
    timing[ys, xs] = np.clip(start + progress * dur, start, start + dur)

    return timing
