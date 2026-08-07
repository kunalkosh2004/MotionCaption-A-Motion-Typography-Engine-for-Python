"""Emphasis subsystem: rule-based word importance and emphasis modes."""

from motion_caption.emphasis.engine import (
    EMPHASIS_REGISTRY,
    apply_emphasis,
    importance_to_mode,
    repetition_counts,
)
from motion_caption.emphasis.scorer import rules_scorer

__all__ = [
    "EMPHASIS_REGISTRY",
    "apply_emphasis",
    "importance_to_mode",
    "repetition_counts",
    "rules_scorer",
]
