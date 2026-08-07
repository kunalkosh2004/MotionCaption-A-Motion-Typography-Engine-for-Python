"""Transcript domain models.

A ``Transcript`` is the semantic input: word-timed tokens. ``Segment`` is a
caption-sized unit produced by the segmentation subsystem. Neither depends on
rendering concepts.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator
from pydantic import AliasChoices


class EmphasisMode(str, Enum):
    """How a word is visually emphasized (decided by the emphasis subsystem)."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    KARAOKE = "karaoke"


class WordTimestamp(BaseModel):
    """A single word with its on/off times. WhisperX-compatible aliases."""

    text: str = Field(min_length=1, validation_alias=AliasChoices("text", "word"))
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_timing(self) -> "WordTimestamp":
        if self.end < self.start:
            raise ValueError(f"word {self.text!r} ends before it starts ({self.start} > {self.end})")
        return self

    @property
    def duration(self) -> float:
        return self.end - self.start


class Transcript(BaseModel):
    """The full word-timed transcript (the semantic input to the engine)."""

    language: str = "en"
    words: list[WordTimestamp] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.words[-1].end if self.words else 0.0

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def word_count(self) -> int:
        return len(self.words)


class Word(BaseModel):
    """A word inside a rendered segment, enriched with emphasis data."""

    text: str = Field(min_length=1)
    start: float = Field(default=0.0, ge=0.0)
    end: float = Field(default=0.0, ge=0.0)
    importance: float = Field(default=0.0, ge=0.0, le=1.0)
    emphasis: EmphasisMode = EmphasisMode.NONE

    @model_validator(mode="after")
    def _check_timing(self) -> "Word":
        if self.end < self.start:
            raise ValueError(f"word {self.text!r} ends before it starts ({self.start} > {self.end})")
        return self

    @property
    def duration(self) -> float:
        return self.end - self.start


class Segment(BaseModel):
    """One caption: a group of words shown together on screen."""

    text: str = Field(min_length=1)
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    words: list[Word] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_timing(self) -> "Segment":
        if self.end < self.start:
            raise ValueError(f"segment ends before it starts ({self.start} > {self.end})")
        return self

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def word_count(self) -> int:
        return len(self.words)
