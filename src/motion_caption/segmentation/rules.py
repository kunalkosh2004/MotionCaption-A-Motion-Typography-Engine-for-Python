"""Segmentation configuration and language-aware break rules.

The splitter's bounds (words, duration, pauses) and the text rules that rank
candidate break points. Rules are English-gated so other languages still get
punctuation- and timing-based splits without fake phrase heuristics.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SegmentationConfig(BaseModel):
    """Bounds and preferences for one segmentation pass."""

    max_words: int = Field(default=6, ge=1)
    target_words: int = Field(default=5, ge=1)
    max_duration: float = Field(default=7.0, gt=0.0)
    min_duration: float = Field(default=0.5, gt=0.0)
    pause_threshold: float = Field(default=0.35, ge=0.0)
    language: str = "en"

    @model_validator(mode="after")
    def _sane_targets(self) -> SegmentationConfig:
        if self.target_words > self.max_words:
            self.target_words = self.max_words
        return self


# Break priorities. Higher = better place to cut. Priority 0 means "avoid".
SENTENCE_BREAK = 5  # after . ! ?
CLAUSE_BREAK = 4  # after , ; : …
CONJUNCTION_BREAK = 3  # before and/but/or/so/...
PREPOSITION_BREAK = 2  # before in/on/of/...
DEFAULT_BREAK = 1  # any word boundary
NO_BREAK = 0  # before articles: keep the phrase intact

_STRONG = frozenset("!?.")
_CLAUSE = frozenset(";:,…—–")

# Breaking before these words would detach them from the phrase they belong
# to, so they are scored 0 (only cut here if caps force it).
_ARTICLES = frozenset({"a", "an", "the"})

# Subordinate / coordinating conjunctions: good to start a new line.
_CONJUNCTIONS = frozenset(
    {
        "and", "but", "or", "so", "nor", "yet", "for", "because", "although",
        "though", "while", "if", "when", "where", "as", "since", "until",
        "unless", "after", "before", "however", "therefore", "then", "despite",
    }
)

# Prepositional-phrase starts: "in the morning" can open a new line.
_PREPOSITIONS = frozenset(
    {
        "in", "on", "at", "of", "for", "with", "by", "from", "to", "about",
        "into", "over", "under", "through", "between", "among", "during",
        "across", "behind", "beyond", "after", "before", "against", "within",
        "without", "around", "along",
    }
)


def _word_key(word: str) -> str:
    return word.strip("\"'“”’()[]{}«»").lower()


def break_priority(previous: str, following: str, language: str = "en") -> int:
    """Score cutting between two words; higher is a better break point."""
    tail = previous.rstrip("\"'“”’()[]{}«»")
    if tail:
        last = tail[-1]
        if last in _STRONG:
            return SENTENCE_BREAK
        if last in _CLAUSE:
            return CLAUSE_BREAK
    if language.lower() != "en":
        return DEFAULT_BREAK
    nxt = _word_key(following)
    if nxt in _ARTICLES:
        return NO_BREAK
    if nxt in _CONJUNCTIONS:
        return CONJUNCTION_BREAK
    if nxt in _PREPOSITIONS:
        return PREPOSITION_BREAK
    return DEFAULT_BREAK


def pause_priority(gap: float, threshold: float) -> int:
    """Silence between words is the strongest natural boundary."""
    return SENTENCE_BREAK if gap > threshold else DEFAULT_BREAK
