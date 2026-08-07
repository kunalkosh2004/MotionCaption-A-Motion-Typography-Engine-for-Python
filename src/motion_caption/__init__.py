"""MotionCaption — Motion Typography Engine for Python.

Deterministic, plugin-based animated subtitles. See ``docs/architecture.md``
for the design contract.
"""

from __future__ import annotations

from motion_caption import models
from motion_caption.canvas import AspectRatio, Canvas, StandardResolution
from motion_caption.models import (
    Box,
    Color,
    DesignSpace,
    EmphasisMode,
    FillSpec,
    GradientFill,
    GradientStop,
    Length,
    Padding,
    Point,
    Resolution,
    ResolutionContext,
    ScalePolicy,
    Segment,
    Size,
    Transcript,
    Unit,
    Word,
    WordTimestamp,
)
from motion_caption.registry import Registry

__version__ = "0.1.0"

__all__ = [
    "AspectRatio",
    "Box",
    "Canvas",
    "Color",
    "DesignSpace",
    "EmphasisMode",
    "FillSpec",
    "GradientFill",
    "GradientStop",
    "Length",
    "Padding",
    "Point",
    "Registry",
    "Resolution",
    "ResolutionContext",
    "ScalePolicy",
    "Segment",
    "Size",
    "StandardResolution",
    "Transcript",
    "Unit",
    "Word",
    "WordTimestamp",
    "models",
]
