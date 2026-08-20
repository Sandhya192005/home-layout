"""Small rectangle/edge geometry helpers used by the floor-plan generator.

A "rect" is a plain dict: {"x": float, "y": float, "w": float, "l": float}
x grows East, y grows South (y=0 is the North edge of the plot) — this matches
the ZONE_GRID convention (row 0 = North, col 0 = West).
"""
from __future__ import annotations

EPS = 1e-6


def rect_x2(r: dict) -> float:
    return r["x"] + r["w"]


def rect_y2(r: dict) -> float:
    return r["y"] + r["l"]


def rect_area(r: dict) -> float:
    return max(r["w"], 0) * max(r["l"], 0)


def shrink_edge(r: dict, edge: str, amount: float) -> dict:
    """Return a new rect with one edge ('north'|'south'|'west'|'east') moved inward by `amount`."""
    r = dict(r)
    amount = max(0.0, min(amount, r["w"] if edge in ("west", "east") else r["l"]))
    if edge == "north":
        r["y"] += amount
        r["l"] -= amount
    elif edge == "south":
        r["l"] -= amount
    elif edge == "west":
        r["x"] += amount
        r["w"] -= amount
    elif edge == "east":
        r["w"] -= amount
    return r


def split_strip(r: dict, side: str, size: float) -> tuple[dict, dict]:
    """Split rect `r` into (strip, remainder) where `strip` is a full-depth/width slice
    of thickness `size` taken from the given side ('west'|'east'|'north'|'south')."""
    size = max(0.0, min(size, r["w"] if side in ("west", "east") else r["l"]))
    if side == "west":
        strip = {"x": r["x"], "y": r["y"], "w": size, "l": r["l"]}
        rest = {"x": r["x"] + size, "y": r["y"], "w": r["w"] - size, "l": r["l"]}
    elif side == "east":
        strip = {"x": r["x"] + r["w"] - size, "y": r["y"], "w": size, "l": r["l"]}
        rest = {"x": r["x"], "y": r["y"], "w": r["w"] - size, "l": r["l"]}
    elif side == "north":
        strip = {"x": r["x"], "y": r["y"], "w": r["w"], "l": size}
        rest = {"x": r["x"], "y": r["y"] + size, "w": r["w"], "l": r["l"] - size}
    else:  # south
        strip = {"x": r["x"], "y": r["y"] + r["l"] - size, "w": r["w"], "l": size}
        rest = {"x": r["x"], "y": r["y"], "w": r["w"], "l": r["l"] - size}
    return strip, rest


def subdivide(r: dict, axis: str, weights: list[float]) -> list[dict]:
    """Split rect `r` along 'x' or 'y' into len(weights) pieces proportional to weights."""
    total = sum(weights) or 1.0
    pieces = []
    offset = 0.0
    dim = r["w"] if axis == "x" else r["l"]
    for wgt in weights:
        size = dim * (wgt / total)
        if axis == "x":
            pieces.append({"x": r["x"] + offset, "y": r["y"], "w": size, "l": r["l"]})
        else:
            pieces.append({"x": r["x"], "y": r["y"] + offset, "w": r["w"], "l": size})
        offset += size
    return pieces


def subdivide_min_aware(r: dict, axis: str, items: list[dict]) -> list[dict]:
    """Like `subdivide`, but each item may carry a `min` size along `axis`
    (`{"weight": float, "min": float}`). When the rect has enough room for
    every minimum, each piece gets at least its min and any leftover space is
    handed out proportional to weight. When it doesn't, space is handed out
    proportional to the mins themselves (so a room that needs more stays
    comparatively bigger than one that needs less, instead of collapsing to
    whatever its raw layout weight happened to be)."""
    n = len(items)
    if n == 0:
        return []
    dim = r["w"] if axis == "x" else r["l"]
    mins = [max(it.get("min", 0.0), 0.0) for it in items]
    weights = [max(it.get("weight", 0.0), 0.0) for it in items]
    sum_min = sum(mins)

    if sum_min <= dim:
        leftover = dim - sum_min
        weight_total = sum(weights)
        sizes = []
        for i in range(n):
            share = (weights[i] / weight_total) if weight_total > 0 else (1.0 / n)
            sizes.append(mins[i] + leftover * share)
    else:
        basis = mins if sum_min > 0 else [1.0] * n
        basis_total = sum(basis)
        sizes = [dim * (b / basis_total) for b in basis]

    pieces = []
    offset = 0.0
    for size in sizes:
        if axis == "x":
            pieces.append({"x": r["x"] + offset, "y": r["y"], "w": size, "l": r["l"]})
        else:
            pieces.append({"x": r["x"], "y": r["y"] + offset, "w": r["w"], "l": size})
        offset += size
    return pieces


def edges_of(r: dict) -> dict[str, tuple[float, float, float, float]]:
    """Return the 4 boundary segments of a rect as (x1, y1, x2, y2), keyed by side."""
    x1, y1, x2, y2 = r["x"], r["y"], rect_x2(r), rect_y2(r)
    return {
        "north": (x1, y1, x2, y1),
        "south": (x1, y2, x2, y2),
        "west": (x1, y1, x1, y2),
        "east": (x2, y1, x2, y2),
    }


def shared_segment(rect_a: dict, rect_b: dict) -> tuple[str, str, tuple[float, float, float, float]] | None:
    """If rect_a and rect_b share a collinear boundary segment, return
    (side_on_a, side_on_b, overlap_segment). Otherwise None."""
    opposite = {"north": "south", "south": "north", "west": "east", "east": "west"}
    edges_a, edges_b = edges_of(rect_a), edges_of(rect_b)
    for side_a, (ax1, ay1, ax2, ay2) in edges_a.items():
        side_b = opposite[side_a]
        bx1, by1, bx2, by2 = edges_b[side_b]
        if side_a in ("north", "south"):
            if abs(ay1 - by1) > EPS:
                continue
            lo = max(min(ax1, ax2), min(bx1, bx2))
            hi = min(max(ax1, ax2), max(bx1, bx2))
            if hi - lo > EPS:
                return side_a, side_b, (lo, ay1, hi, ay1)
        else:
            if abs(ax1 - bx1) > EPS:
                continue
            lo = max(min(ay1, ay2), min(by1, by2))
            hi = min(max(ay1, ay2), max(by1, by2))
            if hi - lo > EPS:
                return side_a, side_b, (ax1, lo, ax1, hi)
    return None


def on_boundary(rect: dict, outline: dict) -> list[str]:
    """Which sides of `rect` lie on the outer `outline` boundary."""
    sides = []
    if abs(rect["x"] - outline["x"]) < EPS:
        sides.append("west")
    if abs(rect_x2(rect) - rect_x2(outline)) < EPS:
        sides.append("east")
    if abs(rect["y"] - outline["y"]) < EPS:
        sides.append("north")
    if abs(rect_y2(rect) - rect_y2(outline)) < EPS:
        sides.append("south")
    return sides


def rects_overlap(a: dict, b: dict) -> bool:
    """True if rects `a` and `b` overlap by more than a sliver (touching edges don't count)."""
    return (
        a["x"] < rect_x2(b) - EPS and rect_x2(a) > b["x"] + EPS and
        a["y"] < rect_y2(b) - EPS and rect_y2(a) > b["y"] + EPS
    )


def segment_length(seg: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = seg
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


def midpoint(seg: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = seg
    return (x1 + x2) / 2, (y1 + y2) / 2
