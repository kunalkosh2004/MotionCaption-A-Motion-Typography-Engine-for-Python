"""Transcript → ``Segment`` segmentation.

The default strategy is a grammar + rhythm aware greedy splitter: pause
silence, sentence, clause, conjunction and preposition boundaries rank as
break candidates; the split is bounded by ``max_words``, ``max_duration``
and rebalanced by ``min_duration``. Plugins register their own strategies
through ``SEGMENTATION_REGISTRY`` (AI providers may propose splits later).
"""

from __future__ import annotations

from collections.abc import Callable

from motion_caption.models.transcript import Segment, Transcript, Word, WordTimestamp
from motion_caption.registry import Registry
from motion_caption.segmentation.rules import (
    CLAUSE_BREAK,
    DEFAULT_BREAK,
    SegmentationConfig,
    break_priority,
    pause_priority,
)

SegmentationStrategy = Callable[[Transcript, SegmentationConfig], list[Segment]]


def _as_word(token: WordTimestamp) -> Word:
    return Word(text=token.text, start=token.start, end=token.end)


def _build(words: list[Word]) -> Segment:
    return Segment(
        text=" ".join(word.text for word in words),
        start=words[0].start,
        end=words[-1].end,
        words=words,
    )


def _priorities(
    words: list[Word],
    config: SegmentationConfig,
    *,
    use_grammar: bool,
    use_pauses: bool,
) -> list[int]:
    """Break score after each word; index i == boundary between i and i+1."""
    if len(words) < 2:
        return []
    scores: list[int] = []
    for index in range(len(words) - 1):
        score = DEFAULT_BREAK
        if use_grammar:
            score = break_priority(words[index].text, words[index + 1].text, config.language)
        if use_pauses:
            gap = words[index + 1].start - words[index].end
            score = max(score, pause_priority(gap, config.pause_threshold))
        scores.append(score)
    return scores


def _greedy_end(
    words: list[Word],
    start: int,
    scores: list[int],
    config: SegmentationConfig,
) -> int:
    """Exclusive end index of the next segment (slice ``words[start:end]``).

    Sentence/clause breaks (priority >= 4) split even inside the caps so each
    caption stays a grammatical unit; weaker breaks only split when a cap
    forces the cut.
    """
    n = len(words)
    hard = start + 1
    for end in range(start + 1, n + 1):
        if end - start > config.max_words:
            break
        if words[end - 1].end - words[start].start > config.max_duration:
            break
        hard = end
    within_caps = hard >= n
    limit = n - 1 if within_caps else hard
    target = start + config.target_words
    best: tuple[int, int, int] | None = None
    for boundary in range(start + 1, limit + 1):
        score = scores[boundary - 1]
        candidate = (score, -abs(boundary - target), boundary)
        if best is None or candidate > best:
            best = candidate
    if within_caps:
        if best is None or best[0] < CLAUSE_BREAK:
            return n
        return best[2]
    return best[2] if best is not None else hard


def _merge_short(segments: list[Segment], config: SegmentationConfig) -> list[Segment]:
    """Fold captions shorter than min_duration into the previous one (safe)."""
    merged: list[Segment] = []
    for segment in segments:
        if merged and segment.duration < config.min_duration:
            previous = merged[-1]
            words = [*previous.words, *segment.words]
            under_words = len(words) <= config.max_words
            under_duration = words[-1].end - words[0].start <= config.max_duration
            if under_words and under_duration:
                merged[-1] = _build(words)
                continue
        merged.append(segment)
    return merged


def _segment(
    transcript: Transcript,
    config: SegmentationConfig,
    *,
    use_grammar: bool,
    use_pauses: bool,
) -> list[Segment]:
    tokens = [_as_word(token) for token in transcript.words]
    if not tokens:
        return []
    scores = _priorities(tokens, config, use_grammar=use_grammar, use_pauses=use_pauses)
    segments: list[Segment] = []
    start = 0
    while start < len(tokens):
        end = _greedy_end(tokens, start, scores, config)
        segments.append(_build(tokens[start:end]))
        start = end
    return _merge_short(segments, config)


def sentence_strategy(transcript: Transcript, config: SegmentationConfig) -> list[Segment]:
    """Grammar + pause-aware greedy segmentation (the default)."""
    return _segment(transcript, config, use_grammar=True, use_pauses=True)


def pauses_strategy(transcript: Transcript, config: SegmentationConfig) -> list[Segment]:
    """Timing-only: cut on silence, then enforce caps."""
    return _segment(transcript, config, use_grammar=False, use_pauses=True)


def strict_strategy(transcript: Transcript, config: SegmentationConfig) -> list[Segment]:
    """Hard caps only; no grammar or pause preference."""
    return _segment(transcript, config, use_grammar=False, use_pauses=False)


SEGMENTATION_REGISTRY: Registry[SegmentationStrategy] = Registry("segmentation")

SEGMENTATION_REGISTRY.add("sentence", sentence_strategy, overwrite=True)
SEGMENTATION_REGISTRY.add("pauses", pauses_strategy, overwrite=True)
SEGMENTATION_REGISTRY.add("strict", strict_strategy, overwrite=True)


def segment_transcript(
    transcript: Transcript,
    config: SegmentationConfig | None = None,
    *,
    strategy: str = "sentence",
) -> list[Segment]:
    """Split a timed transcript into caption segments."""
    resolved = config or SegmentationConfig(language=transcript.language)
    return SEGMENTATION_REGISTRY.get(strategy)(transcript, resolved)


def reading_speed(block: list[Word] | Segment) -> float:
    """Words per second over the block's spoken duration (0 for silence)."""
    if isinstance(block, Segment):
        if block.words:
            words = block.words
            duration = words[-1].end - words[0].start
            count = len(words)
        else:
            duration = block.duration
            count = len(block.text.split())
    else:
        words = block
        if not words:
            return 0.0
        duration = words[-1].end - words[0].start
        count = len(words)
    if duration <= 0.0:
        return 0.0
    return count / duration


class Segmenter:
    """Object facade over a strategy + config for repeated use."""

    def __init__(
        self,
        config: SegmentationConfig | None = None,
        *,
        strategy: str = "sentence",
    ) -> None:
        self.config = config or SegmentationConfig()
        self.strategy = strategy

    def segment(self, transcript: Transcript) -> list[Segment]:
        return segment_transcript(transcript, self.config, strategy=self.strategy)
