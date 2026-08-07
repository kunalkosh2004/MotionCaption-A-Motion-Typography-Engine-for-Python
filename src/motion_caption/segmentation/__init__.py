"""Segmentation subsystem: transcript → caption segments."""

from motion_caption.segmentation.engine import (
    SEGMENTATION_REGISTRY,
    Segmenter,
    pauses_strategy,
    reading_speed,
    segment_transcript,
    sentence_strategy,
    strict_strategy,
)
from motion_caption.segmentation.rules import (
    SegmentationConfig,
    break_priority,
    pause_priority,
)

__all__ = [
    "SEGMENTATION_REGISTRY",
    "SegmentationConfig",
    "Segmenter",
    "break_priority",
    "pause_priority",
    "pauses_strategy",
    "reading_speed",
    "segment_transcript",
    "sentence_strategy",
    "strict_strategy",
]
