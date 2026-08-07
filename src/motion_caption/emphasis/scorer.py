"""Rule-based word importance scoring.

Each word gets a 0..1 importance: how much visual weight it should carry.
Rules cover the emphasis contract: filler words, function words, repetition,
position (sentence-initial / sentence-final prosodic focus) and surface
features (length, capitalization, numerics). Deterministic; no external
lexicons beyond the small closed sets below.
"""

from __future__ import annotations

from collections.abc import Sequence

from motion_caption.models.transcript import Word

_BASE = 0.4

_FILLERS = frozenset(
    {
        "uh", "um", "er", "hmm", "ah", "eh", "like", "you know", "well",
        "actually", "basically", "literally", "okay", "right", "yeah",
        "huh", "y'know", "kinda", "sorta", "anyway", "i mean",
    }
)

_FUNCTION_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "nor", "yet", "so", "for",
        "of", "in", "on", "at", "to", "by", "with", "from", "into", "over",
        "under", "about", "between", "as", "than", "that", "this", "these",
        "those", "it", "its", "he", "she", "we", "they", "them", "his",
        "her", "our", "your", "my", "their", "i", "you", "me", "us", "am",
        "is", "are", "was", "were", "be", "been", "being", "do", "does",
        "did", "have", "has", "had", "will", "would", "can", "could",
        "shall", "should", "may", "might", "must", "not", "no", "yes",
        "there", "here", "when", "where", "while", "who", "whom", "whose",
        "which", "how", "what", "why", "if", "then", "also", "just", "very",
        "really", "much", "many", "some", "any", "more", "most", "all",
        "each", "every", "both", "either", "neither", "one", "two",
    }
)

_STRONG_END = frozenset("!?.")
_SENTENCE_BREAK_BEFORE = _STRONG_END | frozenset(";:")


def _clean(text: str) -> str:
    return text.strip("\"'“”’()[]{}«»—….,;:!?")


def _word_key(text: str) -> str:
    return _clean(text).lower()


def _sentence_end(words: Sequence[Word], index: int) -> bool:
    if index + 1 < len(words):
        return bool(words[index + 1].text.rstrip('"\'”’)]').endswith(tuple(_STRONG_END)))
    return True


def _sentence_start(words: Sequence[Word], index: int) -> bool:
    if index == 0:
        return True
    previous = words[index - 1].text.rstrip('"\'”’)]')
    return bool(previous and previous[-1] in _SENTENCE_BREAK_BEFORE)


def rules_scorer(words: Sequence[Word], repetition_counts: dict[str, int]) -> list[float]:
    """Default importance scorer: 0..1 per word, deterministic."""
    scores: list[float] = []
    for index, word in enumerate(words):
        raw = _clean(word.text)
        key = _word_key(word.text)
        score = _BASE
        if key in _FILLERS:
            score -= 0.35
        elif key in _FUNCTION_WORDS:
            score -= 0.25
        length = len(raw)
        if 0 < length <= 3:
            score -= 0.1
        elif length >= 8:
            score += 0.15
        elif length >= 6:
            score += 0.1
        if repetition_counts.get(key, 0) >= 3:
            score += 0.1
        if _sentence_end(words, index):
            score += 0.1
        elif _sentence_start(words, index):
            score += 0.05
        if (
            raw[:1].isupper()
            and length >= 3
            and not _sentence_start(words, index)
            and key not in _FILLERS
            and key not in _FUNCTION_WORDS
        ):
            score += 0.15
        if any(char.isdigit() for char in raw):
            score += 0.1
        scores.append(min(1.0, max(0.0, score)))
    return scores
