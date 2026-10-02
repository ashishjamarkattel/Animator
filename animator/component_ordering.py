"""Component ordering and spatial grouping.

Pure functions over component dicts (mask + bbox + flags) that decide the
order a hand would draw them: spatial groups, top-down reading order,
containment, and assignment of components to detected region boxes.
"""

from collections import defaultdict

import numpy as np


def assign_components_to_boxes(
    components: list, boxes_px: list
) -> tuple[list, list]:
    """Assign components to pixel bounding boxes in three passes:
    center containment (smallest box wins), >=25% overlap coverage, then
    nearest box center within a proximity limit.

    boxes_px entries are [x1, y1, x2, y2] or None (no box -> never matched).
    Returns (per_box_lists, unmatched).
    """
    scaled = []
    for box in boxes_px:
        if box is None:
            scaled.append(None)
            continue
        x1, y1, x2, y2 = box
        bw = max(x2 - x1, 1)
        bh = max(y2 - y1, 1)
        scaled.append({
            "x1": x1, "y1": y1,
            "x2": x2, "y2": y2,
            "cx": (x1 + x2) / 2,
            "cy": (y1 + y2) / 2,
            "area": bw * bh,
            "diag2": bw * bw + bh * bh,
            "items": [],
        })

    real = [s for s in scaled if s is not None]
    unmatched = []
    for comp in components:
        ccx = (comp["left"] + comp["right"]) / 2.0
        ccy = (comp["top"] + comp["bottom"]) / 2.0
        cw = max(comp["right"] - comp["left"], 1)
        ch = max(comp["bottom"] - comp["top"], 1)
        comp_area = cw * ch
        comp_diag2 = cw * cw + ch * ch

        contained = [
            s for s in real
            if s["x1"] <= ccx <= s["x2"] and s["y1"] <= ccy <= s["y2"]
        ]
        container = min(contained, key=lambda s: s["area"]) if contained else None

        if container is None:
            overlaps = []
            for s in real:
                ix = max(0, min(comp["right"], s["x2"]) - max(comp["left"], s["x1"]))
                iy = max(0, min(comp["bottom"], s["y2"]) - max(comp["top"], s["y1"]))
                coverage = (ix * iy) / max(comp_area, 1)
                if coverage >= 0.25:
                    overlaps.append((coverage, s))
            if overlaps:
                overlaps.sort(key=lambda item: (-item[0], item[1]["area"]))
                container = overlaps[0][1]

        if container is None:
            best = None
            best_score = None
            for s in real:
                dx = ccx - s["cx"]
                dy = ccy - s["cy"]
                d2 = dx * dx + dy * dy
                limit2 = max(s["diag2"] * 0.55, comp_diag2 * 2.25, 90 * 90)
                if d2 > limit2:
                    continue
                score = d2 / max(s["diag2"], 1)
                if best_score is None or score < best_score:
                    best, best_score = s, score
            if best is not None:
                container = best

        if container is None:
            unmatched.append(comp)
        else:
            container["items"].append(comp)

    per_box = [s["items"] if s is not None else [] for s in scaled]
    return per_box, unmatched


def sort_components_layered(components: list) -> list:
    if not components:
        return components

    groups = build_spatial_groups(components)
    group_order = line_bucket_indices(list(range(len(groups))), groups)

    ordered = []
    for gi in group_order:
        ordered.extend(sort_components_reading_order(groups[gi]["items"]))
    return attach_trailing_dots(ordered)


def attach_trailing_dots(ordered: list) -> list:
    """Move glyph dots (question marks, exclamation marks) to draw
    immediately after the mark they belong to. The spatial sort treats a
    dot as its own tiny component and can drop it into a much later line
    bucket, so the dot appears long after its glyph."""
    if len(ordered) < 2:
        return ordered

    result = list(ordered)
    for comp in ordered:
        cw = comp["right"] - comp["left"]
        ch = comp["bottom"] - comp["top"]
        if comp.get("is_fill") or cw > 45 or ch > 45 or comp["area"] > 1200:
            continue
        cx = (comp["left"] + comp["right"]) / 2
        dot_h = max(ch, 1)

        best = None
        best_gap = None
        for parent in ordered:
            if parent is comp or parent["area"] < comp["area"] * 3:
                continue
            if not (parent["left"] - 5 <= cx <= parent["right"] + 5):
                continue
            # The dot sits just below its glyph (slight overlap allowed).
            gap = comp["top"] - parent["bottom"]
            if -dot_h <= gap <= 4 * dot_h:
                if best_gap is None or gap < best_gap:
                    best, best_gap = parent, gap
        if best is None:
            continue

        # Components hold numpy arrays, so list.remove/index (which
        # compare with ==) are unusable; work by identity instead.
        result = [c for c in result if c is not comp]
        parent_index = next(
            i for i, c in enumerate(result) if c is best
        )
        result.insert(parent_index + 1, comp)
    return result


def build_spatial_groups(components: list) -> list:
    if len(components) <= 1:
        return [{
            "items": list(components),
            "top": components[0]["top"],
            "bottom": components[0]["bottom"],
            "left": components[0]["left"],
            "right": components[0]["right"],
        }] if components else []

    parent = list(range(len(components)))

    def find(idx):
        while parent[idx] != idx:
            parent[idx] = parent[parent[idx]]
            idx = parent[idx]
        return idx

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(components)):
        for j in range(i + 1, len(components)):
            if should_group_components(components[i], components[j]):
                union(i, j)

    buckets = defaultdict(list)
    for i, comp in enumerate(components):
        buckets[find(i)].append(comp)

    groups = []
    for items in buckets.values():
        groups.append({
            "items": items,
            "top": min(c["top"] for c in items),
            "bottom": max(c["bottom"] for c in items),
            "left": min(c["left"] for c in items),
            "right": max(c["right"] for c in items),
        })
    return groups


def should_group_components(a: dict, b: dict) -> bool:
    ah = max(a["bottom"] - a["top"], 1)
    bh = max(b["bottom"] - b["top"], 1)
    aw = max(a["right"] - a["left"], 1)
    bw = max(b["right"] - b["left"], 1)

    x_overlap = min(a["right"], b["right"]) - max(a["left"], b["left"])
    y_overlap = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
    x_gap = max(a["left"], b["left"]) - min(a["right"], b["right"])
    y_gap = max(a["top"], b["top"]) - min(a["bottom"], b["bottom"])

    x_overlap_ratio = max(x_overlap, 0) / max(min(aw, bw), 1)
    y_overlap_ratio = max(y_overlap, 0) / max(min(ah, bh), 1)
    width_ratio = max(aw, bw) / max(min(aw, bw), 1)

    if contains_component(a, b) or contains_component(b, a):
        return True

    bridges_columns = width_ratio > 2.8 and max(aw, bw) > min(aw, bw) + 120

    if x_overlap_ratio > 0.25 and y_gap < max(ah, bh) * 1.7:
        return not bridges_columns

    if y_overlap_ratio > 0.35 and x_gap < max(ah, bh, 40) * 1.4:
        return True

    if x_overlap_ratio > 0.55 and y_gap < 90:
        return not bridges_columns

    return False


def contains_component(outer: dict, inner: dict, pad: int = 10) -> bool:
    outer_w = max(outer["right"] - outer["left"], 1)
    outer_h = max(outer["bottom"] - outer["top"], 1)
    inner_w = max(inner["right"] - inner["left"], 1)
    inner_h = max(inner["bottom"] - inner["top"], 1)
    outer_area = outer_w * outer_h
    inner_area = inner_w * inner_h
    if outer_area <= inner_area * 1.08:
        return False

    left = outer["left"] - pad
    right = outer["right"] + pad
    top = outer["top"] - pad
    bottom = outer["bottom"] + pad

    inter_w = max(0, min(right, inner["right"]) - max(left, inner["left"]))
    inter_h = max(0, min(bottom, inner["bottom"]) - max(top, inner["top"]))
    coverage = (inter_w * inter_h) / max(inner_area, 1)

    cx = (inner["left"] + inner["right"]) / 2
    cy = (inner["top"] + inner["bottom"]) / 2
    center_inside = left <= cx <= right and top <= cy <= bottom
    return center_inside and coverage >= 0.85


def sort_components_reading_order(components: list) -> list:
    """Order components how a person would draw them: top-down, then
    left-to-right within each visual line, with outer/containing shapes
    emitted before whatever sits inside them."""
    if not components:
        return components

    indexed = list(enumerate(components))
    parents = [None] * len(components)
    has_containment = False
    for i, comp in indexed:
        containing = [
            (j, outer)
            for j, outer in indexed
            if i != j and contains_component(outer, comp)
        ]
        if containing:
            has_containment = True
            parents[i] = min(
                containing,
                key=lambda item: (
                    (item[1]["right"] - item[1]["left"])
                    * (item[1]["bottom"] - item[1]["top"])
                ),
            )[0]

    if not has_containment:
        order = line_bucket_indices(list(range(len(components))), components)
        return [components[i] for i in order]

    children = defaultdict(list)
    roots = []
    for i, parent in enumerate(parents):
        (roots if parent is None else children[parent]).append(i)

    ordered = []

    def emit(idx):
        ordered.append(components[idx])
        kids = children[idx]
        if kids:
            for c in line_bucket_indices(kids, components):
                emit(c)

    for r in line_bucket_indices(roots, components):
        emit(r)
    return ordered


def line_bucket_indices(indices: list, items: list) -> list:
    """Return `indices` reordered into top-down reading order.

    Items are bucketed into visual lines using midpoint-Y proximity
    (with a height-ratio veto so a tall element doesn't merge with a
    short one), then sorted left-to-right within each line. Used at
    every level: spatial groups, root components, and a parent's
    children inside a containment hierarchy."""
    if not indices:
        return list(indices)

    ordered_idx = sorted(
        indices, key=lambda i: (items[i]["top"] + items[i]["bottom"]) / 2,
    )

    lines = []  # each: [mid_y, tol, [indices], first_h, weight]
    for idx in ordered_idx:
        comp = items[idx]
        ct, cb = comp["top"], comp["bottom"]
        ch = max(cb - ct, 1)
        mid_y = (ct + cb) / 2
        weight = max(comp.get("area", ch), 1)

        matched = None
        for line in lines:
            line_mid, line_tol, _, first_h, _ = line
            height_ratio = max(ch, first_h) / max(min(ch, first_h), 1)
            if height_ratio > 2.5:
                continue
            if abs(mid_y - line_mid) <= line_tol:
                matched = line
                break

        if matched:
            old_weight = matched[4]
            new_weight = old_weight + weight
            matched[0] = (matched[0] * old_weight + mid_y * weight) / new_weight
            matched[4] = new_weight
            matched[2].append(idx)
        else:
            lines.append([mid_y, ch * 0.4, [idx], ch, weight])

    lines.sort(key=lambda l: l[0])

    out = []
    for _, _, idxs, _, _ in lines:
        idxs.sort(key=lambda i: items[i]["left"])
        # Within-line clustering — keep visually adjacent items contiguous,
        # break when a new item is far away or a very different height.
        clusters = []
        for idx in idxs:
            comp = items[idx]
            ch = comp["bottom"] - comp["top"]
            placed = False
            if clusters:
                last = items[clusters[-1][-1]]
                lh = last["bottom"] - last["top"]
                hr = max(ch, lh) / max(min(ch, lh), 1)
                xg = comp["left"] - last["right"]
                if hr < 3.0 and xg < max(ch, lh) * 2.0:
                    clusters[-1].append(idx)
                    placed = True
            if not placed:
                clusters.append([idx])
        for cl in clusters:
            out.extend(cl)

    return out


def order_text_components(subs: list) -> list:
    lines = []
    for sub in sorted(subs, key=lambda c: c["top"]):
        placed = False
        for line in lines:
            r = line[0]
            if sub["top"] <= r["bottom"] and sub["bottom"] >= r["top"]:
                line.append(sub)
                placed = True
                break
        if not placed:
            lines.append([sub])
    for line in lines:
        line.sort(key=lambda c: c["left"])

    return [s for line in lines for s in line]
