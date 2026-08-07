"""MotionCaption — Motion Typography Engine for Python.

Deterministic, plugin-based animated subtitles. See ``docs/architecture.md``
for the design contract.
"""

from __future__ import annotations

from motion_caption import easing, emphasis, models, reading, segmentation, themes, typography
from motion_caption.canvas import AspectRatio, Canvas, StandardResolution
from motion_caption.easing import EasingKind, EasingSpec, compile_spec
from motion_caption.emphasis import apply_emphasis, importance_to_mode
from motion_caption.models import (
    Box,
    Color,
    DesignSpace,
    EmphasisMode,
    FillSpec,
    GradientFill,
    GradientStop,
    Keyframe,
    KeyframeTimeline,
    Length,
    Padding,
    Point,
    PropertyKind,
    Region,
    RegionTimeline,
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
from motion_caption.reading import ReadingStats, adjust_segments, analyze, difficulty_of
from motion_caption.registry import Registry
from motion_caption.segmentation import (
    SegmentationConfig,
    Segmenter,
    segment_transcript,
)
from motion_caption.themes import (
    AnimationPersonality,
    EmphasisAppearance,
    ResolvedTheme,
    ThemeSpec,
    builtin_themes,
    load_theme,
    resolve_theme,
)
from motion_caption.typography import (
    BackgroundSpec,
    FontManager,
    FontRef,
    FontStack,
    MeasuredBlock,
    TextMeasurer,
    TextStyle,
)

__version__ = "0.1.0"

__all__ = [
    "AnimationPersonality",
    "AspectRatio",
    "BackgroundSpec",
    "Box",
    "Canvas",
    "Color",
    "DesignSpace",
    "EmphasisAppearance",
    "EmphasisMode",
    "EasingKind",
    "EasingSpec",
    "FillSpec",
    "GradientFill",
    "GradientStop",
    "FontManager",
    "FontRef",
    "FontStack",
    "Keyframe",
    "KeyframeTimeline",
    "Length",
    "MeasuredBlock",
    "Padding",
    "Point",
    "PropertyKind",
    "ReadingStats",
    "Region",
    "RegionTimeline",
    "Registry",
    "Resolution",
    "ResolutionContext",
    "ResolvedTheme",
    "ScalePolicy",
    "Segment",
    "SegmentationConfig",
    "Segmenter",
    "Size",
    "StandardResolution",
    "TextMeasurer",
    "TextStyle",
    "ThemeSpec",
    "Transcript",
    "Unit",
    "Word",
    "WordTimestamp",
    "adjust_segments",
    "analyze",
    "apply_emphasis",
    "builtin_themes",
    "compile_spec",
    "difficulty_of",
    "easing",
    "emphasis",
    "importance_to_mode",
    "load_theme",
    "models",
    "reading",
    "resolve_theme",
    "segmentation",
    "segment_transcript",
    "themes",
    "typography",
]
