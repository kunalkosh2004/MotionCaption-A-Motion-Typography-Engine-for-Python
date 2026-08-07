"""Placement subsystem: safe areas and face-aware final positioning."""

from motion_caption.placement.engine import (
    PLACEMENT_REGISTRY,
    PlacementConfig,
    place,
)
from motion_caption.placement.faces import Face, avoid_faces
from motion_caption.placement.safe_areas import (
    PLATFORM_SAFE_AREAS,
    SafeArea,
    platform_safe_area,
)

__all__ = [
    "Face",
    "PLACEMENT_REGISTRY",
    "PLATFORM_SAFE_AREAS",
    "PlacementConfig",
    "SafeArea",
    "avoid_faces",
    "place",
    "platform_safe_area",
]
