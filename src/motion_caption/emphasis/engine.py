"""Emphasis engine: per-word importance → EmphasisMode on segments.

Maps transcript segments through a scorer registry, then quantizes each
word's importance into an ``EmphasisMode`` so themes and animation
strategies can style them. ``apply_emphasis`` is functional: input segments
are not mutated.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence

from motion_caption.emphasis.scorer import rules_scorer
from motion_caption.models.transcript import EmphasisMode, Segment, Word
from motion_caption.registry import Registry

EmphasisScorer = Callable[[Sequence[Word], dict[str, int]], list[float]]


def importance_to_mode(
    importance: float, *, high: float = 0.6, medium: float = 0.45, low: float = 0.3
) -> EmphasisMode:
    """Quantize a 0..1 importance into an emphasis mode."""
    if importance >= high:
        return EmphasisMode.HIGH
    if importance >= medium:
        return EmphasisMode.MEDIUM
    if importance >= low:
        return EmphasisMode.LOW
    return EmphasisMode.NONE


def repetition_counts(segments: Sequence[Segment]) -> dict[str, int]:
    """Lower-cased word → how often it appears across all segments."""
    counts: Counter[str] = Counter()
    for segment in segments:
        for word in segment.words:
            counts[word.text.strip("\"'“”’()[]{}«»—….,;:!?").lower()] += 1
    return dict(counts)


EMPHASIS_REGISTRY: Registry[EmphasisScorer] = Registry("emphasis")

EMPHASIS_REGISTRY.add("rules", rules_scorer, overwrite=True)


def _score_words(words: Sequence[Word], counts: dict[str, int], scorer: str) -> list[float]:
    return EMPHASIS_REGISTRY.get(scorer)(words, counts)


def apply_emphasis(
    segments: Sequence[Segment],
    *,
    karaoke: bool = False,
    scorer: str = "rules",
) -> list[Segment]:
    """Return new segments with importance and emphasis set per word."""
    counts = repetition_counts(segments)
    result: list[Segment] = []
    for segment in segments:
        scores = _score_words(segment.words, counts, scorer)
        enriched: list[Word] = []
        for word, importance in zip(segment.words, scores, strict=True):
            mode = EmphasisMode.KARAOKE if karaoke else importance_to_mode(importance)
            enriched.append(
                word.model_copy(update={"importance": importance, "emphasis": mode})
            )
        result.append(
            segment.model_copy(update={"words": enriched})
        )
    return result
