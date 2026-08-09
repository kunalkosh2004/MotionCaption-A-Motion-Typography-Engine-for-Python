"""Transcript providers: protocol, validation, and a deterministic fake.

The pipeline never talks to an ASR engine directly. It consumes a
``TranscriptProvider`` — any object with a ``transcribe(audio_path)`` method
returning a ``motion_caption`` ``Transcript``. Reference adapters live next to
this module (``whisperx``), and ``FakeTranscriptProvider`` provides a
deterministic fixture for tests and demos.

Real ASR output is messy, so two helpers sit between providers and the
compiler:

* ``normalize_transcript`` — sanitizes raw provider output (sorts, clamps
  overlaps, drops degenerate words) without changing the spoken text order.
* ``validate_transcript`` — the hard gate: raises ``InvalidTranscriptError``
  with an actionable hint when the transcript cannot be captioned.

The provider interface deliberately takes a *path*, not a file object: ASR
engines (WhisperX, whisper.cpp, cloud APIs) all want a path on disk.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol

from motion_caption.errors import InvalidTranscriptError
from motion_caption.models import Transcript, WordTimestamp


class TranscriptProvider(Protocol):
    """Anything that turns an audio file into a word-timed ``Transcript``."""

    def transcribe(self, audio_path: str | Path) -> Transcript:
        """Transcribe ``audio_path``; returns a ``Transcript`` (possibly empty)."""
        ...


def _finite(value: float) -> bool:
    return math.isfinite(value)


def normalize_transcript(transcript: Transcript) -> Transcript:
    """Sanitize provider output into strictly-ordered, non-overlapping words.

    - words are kept in speech order (stable sort by start time),
    - words with non-finite or zero-length timing are dropped,
    - each word's ``end`` is clamped to the next word's ``start`` so the
      timeline is monotonic and never overlaps.

    The returned transcript always validates.
    """
    words = [
        word
        for word in transcript.words
        if _finite(word.start)
        and _finite(word.end)
        and word.end > word.start
        and any(char.isalnum() for char in word.text)
    ]
    words.sort(key=lambda word: (word.start, word.text))
    sanitized: list[WordTimestamp] = []
    for index, word in enumerate(words):
        next_start = (
            words[index + 1].start if index + 1 < len(words) else word.end
        )
        end = min(word.end, next_start)
        if end > word.start:
            sanitized.append(word.model_copy(update={"end": end}))
    return Transcript(language=transcript.language, words=sanitized)


def validate_transcript(transcript: Transcript) -> None:
    """Raise ``InvalidTranscriptError`` when the transcript cannot be captioned.

    Checks what the pydantic models cannot: emptiness, non-finite timestamps,
    and non-monotonic (overlapping) word boundaries. The message always ends
    with an actionable hint.
    """
    if not transcript.words:
        raise InvalidTranscriptError(
            "transcript contains no words",
            hint="use a non-empty transcript (or a transcript provider)",
        )
    for index, word in enumerate(transcript.words):
        if not (_finite(word.start) and _finite(word.end)):
            raise InvalidTranscriptError(
                f"word {index} ({word.text!r}) has a non-finite timestamp: "
                f"start={word.start}, end={word.end}",
                hint="re-run transcription; provider emitted NaN/infinity times",
            )
    for index in range(1, len(transcript.words)):
        previous = transcript.words[index - 1]
        current = transcript.words[index]
        if current.start < previous.end:
            raise InvalidTranscriptError(
                f"words overlap: {previous.text!r} ends at {previous.end:g}s but "
                f"{current.text!r} starts at {current.start:g}s",
                hint="run normalize_transcript() to clamp overlapping boundaries",
            )


class FakeTranscriptProvider:
    """Deterministic transcript provider for tests and demos.

    Splits ``text`` on whitespace and gives every word the same duration
    (``per_word`` seconds), back to back — no IO, no randomness, same output
    on every machine. ``transcribe`` ignores ``audio_path`` and returns an
    empty ``Transcript`` for an empty string (so pipeline error handling can
    be exercised deterministically).
    """

    name = "fake"

    def __init__(
        self,
        text: str,
        *,
        per_word: float = 0.45,
        language: str = "en",
        confidence: float = 1.0,
    ) -> None:
        if per_word <= 0:
            raise ValueError(f"per_word must be positive, got {per_word}")
        self.text = text
        self.per_word = per_word
        self.language = language
        self.confidence = confidence

    def transcribe(self, audio_path: str | Path) -> Transcript:
        del audio_path  # deterministic: output does not depend on the file
        words: list[WordTimestamp] = []
        for index, token in enumerate(self.text.split()):
            start = round(index * self.per_word, 6)
            words.append(
                WordTimestamp(
                    text=token,
                    start=start,
                    end=round(start + self.per_word, 6),
                    confidence=self.confidence,
                )
            )
        return Transcript(language=self.language, words=words)
