"""Domain value objects and entities. This layer has no dependencies on the
rest of MotionCaption and is importable in isolation."""

from motion_caption.models.color import (
    Color,
    FillKind,
    FillSpec,
    GradientFill,
    GradientKind,
    GradientStop,
)
from motion_caption.models.geometry import Box, Padding, Point, Size
from motion_caption.models.keyframe import (
    Keyframe,
    KeyframeTimeline,
    PropertyKind,
    Region,
    RegionTimeline,
    interpolate_value,
    value_kind,
)
from motion_caption.models.transcript import (
    EmphasisMode,
    Segment,
    Transcript,
    Word,
    WordTimestamp,
)
from motion_caption.models.units import (
    DesignSpace,
    Length,
    Resolution,
    ResolutionContext,
    ScalePolicy,
    Unit,
)

__all__ = [
    "Box",
    "Color",
    "DesignSpace",
    "EmphasisMode",
    "FillKind",
    "FillSpec",
    "GradientFill",
    "GradientKind",
    "GradientStop",
    "Keyframe",
    "KeyframeTimeline",
    "Length",
    "Padding",
    "Point",
    "PropertyKind",
    "Region",
    "RegionTimeline",
    "Resolution",
    "ResolutionContext",
    "ScalePolicy",
    "Segment",
    "Size",
    "Transcript",
    "Unit",
    "Word",
    "WordTimestamp",
    "interpolate_value",
    "value_kind",
]
