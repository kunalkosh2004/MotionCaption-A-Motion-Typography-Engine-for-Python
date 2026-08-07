"""Placement: safe-area + face-aware final positioning of a placed block.

Strategies are registered in ``PLACEMENT_REGISTRY`` and decide the region a
block occupies; ``place`` translates the block onto that region. The default
strategies are ``bottom``, ``top``, ``center`` and ``face-aware``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel, Field

from motion_caption.canvas import Canvas
from motion_caption.layout.engine import PlacedBlock
from motion_caption.models.geometry import Box
from motion_caption.placement.faces import Face, avoid_faces
from motion_caption.placement.safe_areas import SafeArea, platform_safe_area
from motion_caption.registry import Registry

type PlacementStrategy = Callable[[Canvas, "PlacementConfig", Box, Sequence[Face]], Box]


class PlacementConfig(BaseModel):
    """Options controlling the final region of a caption block."""

    platform: str | None = None
    safe_area: SafeArea | None = None
    strategy: str = "bottom"
    vertical_bias: float = Field(default=1.0, ge=0.0, le=1.0)
    horizontal_bias: float = Field(default=0.5, ge=0.0, le=1.0)
    face_margin: float = Field(default=0.0, ge=0.0)

    model_config = {"arbitrary_types_allowed": True}


PLACEMENT_REGISTRY: Registry[PlacementStrategy] = Registry("placement")


def _safe_region(canvas: Canvas, config: PlacementConfig) -> Box:
    if config.safe_area is not None:
        return config.safe_area.resolve(canvas)
    if config.platform is not None:
        return platform_safe_area(config.platform).resolve(canvas)
    return Box(0.0, 0.0, float(canvas.width), float(canvas.height))


def _snap(
    canvas: Canvas, config: PlacementConfig, box: Box, faces: Sequence[Face]
) -> Box:
    region = _safe_region(canvas, config)
    x = region.left + (region.width - box.width) * config.horizontal_bias
    y = region.top + (region.height - box.height) * config.vertical_bias
    x = max(region.left, min(x, region.right - box.width))
    y = max(region.top, min(y, region.bottom - box.height))
    return Box.from_xywh(x, y, box.width, box.height)


def _bottom(
    canvas: Canvas, config: PlacementConfig, box: Box, faces: Sequence[Face]
) -> Box:
    return _snap(canvas, config.model_copy(update={"vertical_bias": 1.0}), box, faces)


def _top(
    canvas: Canvas, config: PlacementConfig, box: Box, faces: Sequence[Face]
) -> Box:
    return _snap(canvas, config.model_copy(update={"vertical_bias": 0.0}), box, faces)


def _center(
    canvas: Canvas, config: PlacementConfig, box: Box, faces: Sequence[Face]
) -> Box:
    centered = config.model_copy(update={"vertical_bias": 0.5, "horizontal_bias": 0.5})
    return _snap(canvas, centered, box, faces)


def _face_aware(
    canvas: Canvas, config: PlacementConfig, box: Box, faces: Sequence[Face]
) -> Box:
    placed = _snap(canvas, config, box, faces)
    if not faces:
        return placed
    return avoid_faces(
        placed,
        faces,
        Box(0.0, 0.0, float(canvas.width), float(canvas.height)),
        margin=config.face_margin,
    )


PLACEMENT_REGISTRY.add("bottom", _bottom, overwrite=True)
PLACEMENT_REGISTRY.add("top", _top, overwrite=True)
PLACEMENT_REGISTRY.add("center", _center, overwrite=True)
PLACEMENT_REGISTRY.add("face-aware", _face_aware, overwrite=True)


def place(
    placed: PlacedBlock,
    canvas: Canvas,
    *,
    config: PlacementConfig | None = None,
    faces: Sequence[Face] = (),
) -> PlacedBlock:
    """Apply a placement strategy and translate the block to its final region."""
    config = config or PlacementConfig()
    try:
        strategy = PLACEMENT_REGISTRY.get(config.strategy)
    except KeyError:
        raise KeyError(f"no placement strategy registered: {config.strategy!r}") from None
    final_box = strategy(canvas, config, placed.box, tuple(faces))
    return placed.translate(final_box.left - placed.box.left, final_box.top - placed.box.top)
