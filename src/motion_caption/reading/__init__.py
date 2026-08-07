"""Reading subsystem: pacing, difficulty and readability metrics."""

from motion_caption.reading.engine import (
    DEFAULT_TARGET_WPS,
    ReadingStats,
    adjust_segments,
    analyze,
    difficulty_of,
)

__all__ = [
    "DEFAULT_TARGET_WPS",
    "ReadingStats",
    "adjust_segments",
    "analyze",
    "difficulty_of",
]
