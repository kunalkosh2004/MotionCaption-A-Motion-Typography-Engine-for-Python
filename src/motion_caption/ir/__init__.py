"""Canonical intermediate representation (IR) and unified compiler input.

Everything here is pure data. ``SubtitleTimeline`` imports only ``models/``
primitives; ``CaptionRequest`` is the single serializable input to the
compiler. Backends (exporters, rasterizers) consume the IR and nothing else.
"""

from __future__ import annotations

from motion_caption.ir.request import (
    AIContribution,
    CaptionRequest,
    CompileOptions,
    SpeakerTrack,
)
from motion_caption.ir.timeline import (
    AnimationTrack,
    KeyframeTrack,
    PlacementRegion,
    StyleTrack,
    SubtitleEvent,
    SubtitleTimeline,
    Track,
    WordEvent,
)
from motion_caption.ir.typography import (
    ResolvedBackground,
    ResolvedBorder,
    ResolvedFont,
    ResolvedGlow,
    ResolvedPadding,
    ResolvedShadow,
    ResolvedStroke,
    ResolvedTypography,
)

__all__ = [
    "AIContribution",
    "AnimationTrack",
    "CaptionRequest",
    "CompileOptions",
    "KeyframeTrack",
    "PlacementRegion",
    "ResolvedBackground",
    "ResolvedBorder",
    "ResolvedFont",
    "ResolvedGlow",
    "ResolvedPadding",
    "ResolvedShadow",
    "ResolvedStroke",
    "ResolvedTypography",
    "SpeakerTrack",
    "StyleTrack",
    "SubtitleEvent",
    "SubtitleTimeline",
    "Track",
    "WordEvent",
]
