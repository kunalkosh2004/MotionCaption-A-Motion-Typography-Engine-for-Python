"""Face-aware avoidance: never place captions over eyes, mouth or face."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from motion_caption.models.geometry import Box


class Face(BaseModel):
    """A detected face bounding box (from the AI provider in later phases)."""

    box: Box
    label: str = "face"

    model_config = {"arbitrary_types_allowed": True}


def _overlaps(a: Box, b: Box, margin: float) -> bool:
    return not (
        a.right + margin <= b.left
        or b.right + margin <= a.left
        or a.bottom + margin <= b.top
        or b.bottom + margin <= a.top
    )


def avoid_faces(
    region: Box,
    faces: Sequence[Face],
    canvas: Box,
    *,
    margin: float = 0.0,
) -> Box:
    """Reposition ``region`` so it never overlaps any face.

    Picks the candidate (above/below/left/right of the intersecting faces)
    with the smallest displacement, preferring vertical moves (cost = ``dy``
    vs ``2 * dx``) since captions read top-to-bottom. If no candidate fits
    both the canvas and every face, the region is clamped into the canvas as
    a best effort.
    """
    blockers = [face.box for face in faces if _overlaps(region, face.box, margin)]
    if not blockers:
        return region

    above = min(block.top for block in blockers) - margin - region.height
    below = max(block.bottom for block in blockers) + margin
    left = min(block.left for block in blockers) - margin - region.width
    right = max(block.right for block in blockers) + margin

    candidates = [
        (region.left, above),
        (region.left, below),
        (left, region.top),
        (right, region.top),
    ]
    in_canvas = Box(0.0, 0.0, canvas.width, canvas.height)

    best: Box | None = None
    best_cost = float("inf")
    for x, y in candidates:
        candidate = Box.from_xywh(x, y, region.width, region.height)
        fits = candidate.left >= in_canvas.left and candidate.top >= in_canvas.top
        fits = fits and candidate.right <= in_canvas.right and candidate.bottom <= in_canvas.bottom
        if not fits:
            continue
        if any(_overlaps(candidate, block, margin) for block in blockers):
            continue
        cost = abs(candidate.top - region.top) + 2.0 * abs(candidate.left - region.left)
        if cost < best_cost:
            best_cost = cost
            best = candidate

    if best is not None:
        return best

    clamped = Box(
        left=min(max(region.left, 0.0), in_canvas.right - region.width),
        top=min(max(region.top, 0.0), in_canvas.bottom - region.height),
        right=region.right,
        bottom=region.bottom,
    )
    return Box.from_xywh(clamped.left, clamped.top, region.width, region.height)
