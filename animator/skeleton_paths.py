"""Skeleton graph tracing for stroke animation.

Decomposes a stroke's skeleton into paths between endpoints/junctions and
orders them into sequential pen strokes, so multi-branch line art (an X, a
plus, an arrow with its head, grids, wheels) draws one path after another
the way a hand would, instead of BFS growing every branch at once.
"""

from collections import deque

import cv2
import numpy as np
from scipy import ndimage


def skeleton_degree(skeleton: np.ndarray) -> np.ndarray:
    kernel = np.ones((3, 3), dtype=np.uint8)
    neighbors = cv2.filter2D(
        skeleton.astype(np.uint8), cv2.CV_16S, kernel,
        borderType=cv2.BORDER_CONSTANT,
    )
    return neighbors - skeleton.astype(np.int16)


def iter_neighbors(mask: np.ndarray, y: int, x: int):
    h, w = mask.shape
    y0, y1 = max(y - 1, 0), min(y + 1, h - 1)
    x0, x1 = max(x - 1, 0), min(x + 1, w - 1)
    for ny in range(y0, y1 + 1):
        for nx in range(x0, x1 + 1):
            if ny == y and nx == x:
                continue
            if mask[ny, nx]:
                yield ny, nx


def bfs_skeleton(skeleton, start):
    """BFS along skeleton pixels using a deque.

    O(skeleton_length) instead of O(diameter × crop_area) for the
    old iterative-dilation approach.
    """
    h, w = skeleton.shape
    dists = np.full((h, w), np.inf, dtype=np.float32)
    sy, sx = start
    if sy < 0 or sy >= h or sx < 0 or sx >= w or not skeleton[sy, sx]:
        return dists

    dists[sy, sx] = 0.0
    q = deque([(sy, sx)])

    while q:
        y, x = q.popleft()
        nd = dists[y, x] + 1.0
        # Unrolled 8-neighbor loop
        y0, y1 = max(y - 1, 0), min(y + 1, h - 1)
        x0, x1 = max(x - 1, 0), min(x + 1, w - 1)
        for ny in range(y0, y1 + 1):
            for nx in range(x0, x1 + 1):
                if skeleton[ny, nx] and dists[ny, nx] == np.inf:
                    dists[ny, nx] = nd
                    q.append((ny, nx))
    return dists


def unique_coords(coords: np.ndarray) -> np.ndarray:
    if len(coords) == 0:
        return coords.reshape(0, 2).astype(np.int32)
    coords = coords.astype(np.int32)
    keys = (coords[:, 0].astype(np.int64) << 32) | coords[:, 1].astype(np.int64)
    _, idx = np.unique(keys, return_index=True)
    return coords[np.sort(idx)]


def stroke_progress(stroke: dict, coords: np.ndarray) -> np.ndarray:
    values = stroke["rank"].astype(np.float32)

    span = float(values.max() - values.min()) if len(values) else 0.0
    if span <= 1e-6:
        return np.zeros(len(coords), dtype=np.float32)
    return ((values - values.min()) / span).astype(np.float32)


def oriented_core(path: dict, from_start: bool) -> np.ndarray:
    """Return path pixels ordered away from the selected junction side."""
    coords = np.asarray(path.get("core", path["coords"]), dtype=np.int32)
    if coords.ndim != 2 or coords.shape[1] != 2:
        coords = np.asarray(path["coords"], dtype=np.int32).reshape(-1, 2)
    return coords if from_start else coords[::-1]


def outward_direction(path: dict, from_start: bool) -> np.ndarray:
    """Unit tangent pointing from a junction into a path."""
    coords = oriented_core(path, from_start)
    if len(coords) < 2:
        return np.zeros(2, dtype=np.float32)
    lookahead = min(5, len(coords) - 1)
    direction = coords[lookahead].astype(np.float32) - coords[0].astype(np.float32)
    norm = float(np.linalg.norm(direction))
    if norm <= 1e-6:
        return np.zeros(2, dtype=np.float32)
    return direction / norm


def pair_junction_branches(paths: list) -> dict:
    """Pair incident path ends into the straightest continuations.

    Skeleton extraction cuts every line at a junction. Pairing the most
    opposite outward tangents reconstructs the original pen strokes: the top
    and bottom arms of a plus become one stroke, as do its left and right
    arms. Unpaired arms become separate pen strokes.
    """
    incident: dict[int, list[tuple[int, bool]]] = {}
    for index, path in enumerate(paths):
        start_node = path.get("start_node")
        end_node = path.get("end_node")
        if start_node is not None:
            incident.setdefault(start_node, []).append((index, True))
        if end_node is not None:
            incident.setdefault(end_node, []).append((index, False))

    pairings = {}
    for tokens in incident.values():
        available = set(tokens)
        candidates = []
        for left_index in range(len(tokens)):
            left = tokens[left_index]
            left_direction = outward_direction(paths[left[0]], left[1])
            if not left_direction.any():
                continue
            for right_index in range(left_index + 1, len(tokens)):
                right = tokens[right_index]
                if left[0] == right[0]:
                    continue
                right_direction = outward_direction(paths[right[0]], right[1])
                if not right_direction.any():
                    continue
                # Opposite outward tangents form the straightest continuous
                # stroke through the junction, so lower cosine is better.
                cosine = float(np.dot(left_direction, right_direction))
                candidates.append((cosine, left, right))

        for _cosine, left, right in sorted(candidates, key=lambda item: item[0]):
            if left not in available or right not in available:
                continue
            pairings[left] = right
            pairings[right] = left
            available.remove(left)
            available.remove(right)

    return pairings


def build_line_art_strokes(paths: list, skel_crop: np.ndarray) -> list:
    del skel_crop  # Kept in the signature for animator/test compatibility.
    paths = [path for path in paths if len(path["coords"]) >= 2]
    if not paths:
        return []

    pairings = pair_junction_branches(paths)
    used_paths = set()
    strokes = []

    def token_position(token: tuple[int, bool]) -> tuple:
        path_index, from_start = token
        path = paths[path_index]
        point = path["start"] if from_start else path["end"]
        endpoint = (
            path.get("start_is_endpoint")
            if from_start else path.get("end_is_endpoint")
        )
        return (0 if endpoint else 1, float(point[0]), float(point[1]))

    def append_trail(first_token: tuple[int, bool]) -> None:
        trail = []
        token = first_token
        while token is not None:
            path_index, from_start = token
            if path_index in used_paths:
                break
            path = paths[path_index]
            if (
                    path.get("start_node") is None
                    and path.get("end_node") is None
            ):
                # A closed path has no endpoint tangent to pair. Preserve one
                # stable contour front beginning at its top-left pixel.
                coords = np.asarray(path["coords"], dtype=np.int32)
                first = min(
                    range(len(coords)),
                    key=lambda index: (
                        int(coords[index, 0]), int(coords[index, 1]),
                    ),
                )
                coords = np.roll(coords, -first, axis=0)
            else:
                coords = oriented_core(path, from_start)
            if len(coords):
                trail.append(coords)
            used_paths.add(path_index)

            exit_token = (path_index, not from_start)
            token = pairings.get(exit_token)

        if not trail:
            return
        coords = unique_coords(np.concatenate(trail, axis=0))
        if len(coords) < 2:
            return
        strokes.append({
            "coords": coords,
            "rank": np.arange(len(coords), dtype=np.float32),
            "weight": len(coords),
        })

    # Begin at natural or unpaired ends. Following the precomputed junction
    # pairings then produces complete endpoint-to-endpoint pen strokes.
    start_tokens = []
    for index, path in enumerate(paths):
        for from_start, node_key in (
                (True, "start_node"), (False, "end_node")):
            token = (index, from_start)
            if path.get(node_key) is None or token not in pairings:
                start_tokens.append(token)
    for token in sorted(start_tokens, key=token_position):
        append_trail(token)

    # Closed graphs can have every end paired. Start any remaining trail from
    # its stable top-left side and follow the same continuity map.
    while len(used_paths) < len(paths):
        choices = []
        for index, path in enumerate(paths):
            if index in used_paths:
                continue
            choices.extend(((index, True), (index, False)))
        append_trail(min(choices, key=token_position))

    return strokes


def extract_skeleton_paths(skeleton: np.ndarray) -> list:
    degree = skeleton_degree(skeleton)
    node_mask = skeleton & (degree != 2)
    labeled_nodes, n_nodes = ndimage.label(node_mask.astype(np.uint8))

    if n_nodes == 0:
        return extract_cycle_paths(skeleton)

    node_pixels = {}
    node_centers = {}
    node_objects = ndimage.find_objects(labeled_nodes)
    for node_id, sl in enumerate(node_objects, 1):
        if sl is None:
            continue
        ys_local, xs_local = np.where(labeled_nodes[sl] == node_id)
        if len(ys_local) == 0:
            continue
        ys = ys_local + sl[0].start
        xs = xs_local + sl[1].start
        pts = np.column_stack((ys, xs)).astype(np.int32)
        node_pixels[node_id] = pts
        node_centers[node_id] = (float(ys.mean()), float(xs.mean()))

    visited = np.zeros(skeleton.shape, dtype=bool)
    paths = []
    for node_id, pts in node_pixels.items():
        for py, px in pts:
            for ny, nx in iter_neighbors(skeleton, int(py), int(px)):
                if node_mask[ny, nx] or visited[ny, nx]:
                    continue
                path = walk_skeleton_path(
                    skeleton, node_mask, labeled_nodes, visited,
                    node_id, (int(py), int(px)), (int(ny), int(nx)),
                )
                if path:
                    append_skeleton_path(
                        paths, path, node_pixels, node_centers, degree,
                    )

    if not paths:
        return extract_cycle_paths(skeleton)
    return paths


def walk_skeleton_path(
        skeleton: np.ndarray,
        node_mask: np.ndarray,
        labeled_nodes: np.ndarray,
        visited: np.ndarray,
        start_node: int,
        prev: tuple[int, int],
        curr: tuple[int, int],
) -> dict | None:
    core = []
    end_node = None
    while True:
        y, x = curr
        if node_mask[y, x]:
            end_node = int(labeled_nodes[y, x])
            break
        if visited[y, x]:
            break

        visited[y, x] = True
        core.append((y, x))
        neighbors = [
            p for p in iter_neighbors(skeleton, y, x)
            if p != prev
        ]
        node_neighbors = [p for p in neighbors if node_mask[p]]
        if node_neighbors:
            end_node = int(labeled_nodes[node_neighbors[0]])
            break

        next_pixels = [p for p in neighbors if not node_mask[p] and not visited[p]]
        if not next_pixels:
            break
        prev, curr = curr, next_pixels[0]

    if len(core) < 2:
        return None
    return {
        "start_node": start_node,
        "end_node": end_node,
        "core": np.array(core, dtype=np.int32),
    }


def append_skeleton_path(
        paths: list, path: dict, node_pixels: dict,
        node_centers: dict, degree: np.ndarray,
):
    start_node = path["start_node"]
    end_node = path["end_node"]
    pieces = [node_pixels[start_node], path["core"]]
    start = node_centers[start_node]
    end = (
        node_centers[end_node]
        if end_node in node_centers
        else tuple(path["core"][-1].astype(float))
    )
    if end_node in node_pixels:
        pieces.append(node_pixels[end_node])

    coords = unique_coords(np.concatenate(pieces, axis=0))
    paths.append({
        "coords": coords,
        "core": path["core"],
        "start_node": start_node,
        "end_node": end_node,
        "start": start,
        "end": end,
        "top": int(coords[:, 0].min()),
        "left": int(coords[:, 1].min()),
        "start_is_endpoint": bool(
            np.any(degree[tuple(node_pixels[start_node].T)] == 1)
            and not np.any(degree[tuple(node_pixels[start_node].T)] >= 3)
        ),
        "end_is_endpoint": bool(
            end_node in node_pixels
            and np.any(degree[tuple(node_pixels[end_node].T)] == 1)
            and not np.any(degree[tuple(node_pixels[end_node].T)] >= 3)
        ),
    })


def extract_cycle_paths(skeleton: np.ndarray) -> list:
    contours, _ = cv2.findContours(
        skeleton.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    paths = []
    for contour in contours:
        coords_xy = contour.reshape(-1, 2)
        if len(coords_xy) < 4:
            continue
        coords = np.column_stack((coords_xy[:, 1], coords_xy[:, 0])).astype(np.int32)
        coords = unique_coords(coords)
        paths.append({
            "coords": coords,
            "core": coords,
            "start": tuple(coords[0].astype(float)),
            "end": tuple(coords[-1].astype(float)),
            "top": int(coords[:, 0].min()),
            "left": int(coords[:, 1].min()),
        })
    return paths
