"""Reading engine: pacing, difficulty and readability adjustment.

Keeps on-screen text readable: computes words-per-second, difficulty and
density, then extends segment end times so captions stay on screen long
enough for the target reading speed — without ever overlapping the next
caption.
"""

from __future__ import annotations

from dataclasses import dataclass

from motion_caption.models.transcript import Segment

DEFAULT_TARGET_WPS = 2.2  # ~13 words per 6 seconds, common subtitle guideline


@dataclass(frozen=True, slots=True)
class ReadingStats:
    """Readability metrics for one caption block."""

    word_count: int
    duration: float
    words_per_second: float
    difficulty: float  # 0..1
    density: float  # wps relative to target (1.0 = exactly on target)
    needed_duration: float  # seconds needed to be readable at target_wps
    target_wps: float


def difficulty_of(text: str) -> float:
    """Lexical difficulty 0..1 from word length distribution."""
    words = [word.strip("\"'“”’()[]{}«»—….,;:!?") for word in text.split()]
    if not words:
        return 0.0
    lengths = [len(word) for word in words if word]
    average = sum(lengths) / len(lengths) if lengths else 0.0
    long_ratio = sum(1 for length in lengths if length >= 7) / len(lengths)
    return min(1.0, 0.5 * max(0.0, (average - 4.0) / 6.0) + 0.5 * long_ratio)


def analyze(segment: Segment, *, target_wps: float = DEFAULT_TARGET_WPS) -> ReadingStats:
    """Compute readability stats for a segment."""
    word_count = len(segment.words) or len(segment.text.split())
    duration = segment.duration
    if segment.words:
        spoken = segment.words[-1].end - segment.words[0].start
        if spoken > 0.0:
            duration = spoken
    wps = word_count / duration if duration > 0.0 else 0.0
    needed = word_count / target_wps if target_wps > 0 else duration
    return ReadingStats(
        word_count=word_count,
        duration=duration,
        words_per_second=wps,
        difficulty=difficulty_of(segment.text),
        density=wps / target_wps if target_wps else 0.0,
        needed_duration=needed,
        target_wps=target_wps,
    )


def _extended_end(segment: Segment, next_start: float | None, needed: float) -> float:
    desired = segment.start + needed
    if next_start is not None:
        desired = min(desired, max(segment.end, next_start))
    return max(segment.end, desired)


def adjust_segments(
    segments: list[Segment],
    *,
    target_wps: float = DEFAULT_TARGET_WPS,
) -> list[Segment]:
    """Extend segment end times to stay readable without overlapping.

    Each caption's end is pushed out to the duration its word count needs at
    ``target_wps``, capped at the next caption's start so captions never
    overlap.
    """
    result: list[Segment] = []
    for index, segment in enumerate(segments):
        stats = analyze(segment, target_wps=target_wps)
        next_start = segments[index + 1].start if index + 1 < len(segments) else None
        end = _extended_end(segment, next_start, stats.needed_duration)
        result.append(segment.model_copy(update={"end": end}))
    return result
