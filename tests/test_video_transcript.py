"""Transcript provider, normalization and validation tests."""

from __future__ import annotations

import math

import pytest

from motion_caption.errors import InvalidTranscriptError
from motion_caption.models import Transcript, WordTimestamp
from motion_caption.video.transcript import (
    FakeTranscriptProvider,
    TranscriptProvider,
    normalize_transcript,
    validate_transcript,
)


def _word(text: str, start: float, end: float) -> WordTimestamp:
    return WordTimestamp(text=text, start=start, end=end)


def _transcript(*words: WordTimestamp) -> Transcript:
    return Transcript(words=list(words))


# --- FakeTranscriptProvider -------------------------------------------------


def test_fake_provider_is_deterministic() -> None:
    text = "hello motion typography engine"
    first = FakeTranscriptProvider(text).transcribe("ignored.wav")
    second = FakeTranscriptProvider(text).transcribe("ignored.wav")
    assert first.model_dump() == second.model_dump()


def test_fake_provider_word_timings() -> None:
    transcript = FakeTranscriptProvider("one two three", per_word=0.5).transcribe("a.wav")
    assert [word.text for word in transcript.words] == ["one", "two", "three"]
    assert transcript.words[0].start == 0.0
    assert transcript.words[0].end == 0.5
    assert transcript.words[2].start == 1.0
    assert transcript.words[2].end == 1.5
    assert transcript.duration == 1.5


def test_fake_provider_empty_text_yields_empty_transcript() -> None:
    transcript = FakeTranscriptProvider("   ").transcribe("a.wav")
    assert transcript.words == []


def test_fake_provider_rejects_bad_duration() -> None:
    with pytest.raises(ValueError, match="per_word"):
        FakeTranscriptProvider("x", per_word=0)


# --- validation -------------------------------------------------------------


def test_validate_accepts_clean_transcript() -> None:
    validate_transcript(_transcript(_word("a", 0.0, 0.5), _word("b", 0.5, 1.0)))


def test_validate_empty_transcript_raises_with_hint() -> None:
    with pytest.raises(InvalidTranscriptError, match="no words") as exc_info:
        validate_transcript(_transcript())
    assert exc_info.value.hint


def test_validate_non_finite_timestamp_raises() -> None:
    with pytest.raises(InvalidTranscriptError, match="non-finite"):
        validate_transcript(
            _transcript(WordTimestamp(text="a", start=0.0, end=math.inf))
        )


def test_validate_overlapping_words_raise() -> None:
    with pytest.raises(InvalidTranscriptError, match="overlap"):
        validate_transcript(_transcript(_word("a", 0.0, 1.0), _word("b", 0.8, 1.5)))


# --- normalization ----------------------------------------------------------


def test_normalize_drops_degenerate_words() -> None:
    result = normalize_transcript(
        _transcript(
            WordTimestamp(text="zero", start=0.0, end=0.0),  # zero-length
            _word("ok", 1.0, 1.5),
        )
    )
    assert [word.text for word in result.words] == ["ok"]


def test_normalize_sorts_out_of_order_words() -> None:
    result = normalize_transcript(
        _transcript(_word("late", 2.0, 2.5), _word("early", 0.5, 1.0))
    )
    assert [word.text for word in result.words] == ["early", "late"]


def test_normalize_clamps_overlapping_boundaries() -> None:
    result = normalize_transcript(
        _transcript(_word("a", 0.0, 1.0), _word("b", 0.8, 1.5), _word("c", 1.2, 2.0))
    )
    assert result.words[0].end == 0.8  # clamped to next start
    assert result.words[1].end == 1.2
    assert result.words[2].end == 2.0
    validate_transcript(result)


def test_normalize_output_always_validates() -> None:
    raw = _transcript(
        WordTimestamp(text="x", start=0.0, end=0.0),
        _word("hello", 2.0, 3.0),
        _word("world", 2.5, 4.0),
    )
    validate_transcript(normalize_transcript(raw))


def test_normalize_preserves_language() -> None:
    result = normalize_transcript(Transcript(language="hi", words=[_word("a", 0.0, 1.0)]))
    assert result.language == "hi"


def test_normalize_drops_punctuation_only_words() -> None:
    """ASR noise like "," or "!" must never be captioned."""
    result = normalize_transcript(
        _transcript(
            _word(",", 0.0, 1.0),
            _word("ना", 1.0, 1.5),  # Devanagari counts as alphanumeric
            _word("!", 1.5, 2.0),
            _word("   ", 2.0, 2.5),
        )
    )
    assert [word.text for word in result.words] == ["ना"]


# --- protocol shape ---------------------------------------------------------


def test_fake_provider_satisfies_protocol() -> None:
    provider: TranscriptProvider = FakeTranscriptProvider("hello")
    assert isinstance(provider, FakeTranscriptProvider)
    assert provider.name == "fake"
