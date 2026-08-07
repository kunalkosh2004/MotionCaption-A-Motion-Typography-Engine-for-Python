import pytest

from motion_caption import Segment, Word, apply_emphasis, importance_to_mode
from motion_caption.emphasis import EMPHASIS_REGISTRY, repetition_counts, rules_scorer
from motion_caption.models.transcript import EmphasisMode


def _segment(*texts):
    words = [Word(text=text, start=i, end=i + 0.5) for i, text in enumerate(texts)]
    return Segment(text=" ".join(texts), start=0.0, end=len(texts) * 0.6, words=words)


class TestScorer:
    def test_filler_word_is_low(self):
        score = rules_scorer([Word(text="um", start=0, end=0.5)], {})[0]
        assert score < 0.3

    def test_function_word_is_low(self):
        score = rules_scorer([Word(text="the", start=0, end=0.5)], {})[0]
        assert score < 0.3

    def test_long_word_scores_above_short(self):
        words = [Word(text="a", start=0, end=0.5), Word(text="ambitious", start=0, end=0.5)]
        short, long_ = rules_scorer(words, {})
        assert long_ > short

    def test_repetition_boosts(self):
        word = Word(text="Jupiter", start=0, end=0.5)
        base = rules_scorer([word], {})[0]
        boosted = rules_scorer([word], {"jupiter": 3})[0]
        assert boosted > base

    def test_sentence_final_boost(self):
        words = [Word(text="the", start=0, end=0.5), Word(text="mission.", start=0, end=0.5)]
        mid, final = rules_scorer(words, {})
        assert final > mid

    def test_proper_noun_boost(self):
        words = [
            Word(text="we", start=0, end=0.5),
            Word(text="saw", start=0, end=0.5),
            Word(text="Jupiter", start=0, end=0.5),
        ]
        scores = rules_scorer(words, {})
        assert scores[2] >= 0.5
        assert scores[0] < scores[2]

    def test_numeric_boost(self):
        words = [Word(text="voted", start=0, end=0.5), Word(text="2024", start=0, end=0.5)]
        voted, year = rules_scorer(words, {})
        assert year > voted

    def test_scores_clamped(self):
        words = [Word(text="antidisestablishmentarianism", start=0, end=0.5)]
        assert 0.0 <= rules_scorer(words, {"antidisestablishmentarianism": 10})[0] <= 1.0


class TestModeQuantization:
    def test_thresholds(self):
        assert importance_to_mode(0.7) == EmphasisMode.HIGH
        assert importance_to_mode(0.5) == EmphasisMode.MEDIUM
        assert importance_to_mode(0.35) == EmphasisMode.LOW
        assert importance_to_mode(0.2) == EmphasisMode.NONE

    def test_custom_thresholds(self):
        assert importance_to_mode(0.7, high=0.9) == EmphasisMode.MEDIUM


class TestApplyEmphasis:
    def test_sets_importance_and_mode(self):
        segments = [_segment("We", "saw", "ambitious", "Jupiter.")]
        result = apply_emphasis(segments)
        words = result[0].words
        assert all(word.importance > 0.0 for word in words[2:])
        assert words[2].emphasis == EmphasisMode.HIGH
        assert words[0].emphasis == EmphasisMode.NONE

    def test_does_not_mutate_input(self):
        segments = [_segment("ambitious")]
        result = apply_emphasis(segments)
        assert segments[0].words[0].importance == 0.0
        assert result[0].words[0].importance > 0.0

    def test_karaoke_mode(self):
        result = apply_emphasis([_segment("la", "la", "la")], karaoke=True)
        assert all(word.emphasis == EmphasisMode.KARAOKE for word in result[0].words)

    def test_empty(self):
        assert apply_emphasis([]) == []


class TestRepetition:
    def test_counts_across_segments(self):
        segments = [
            _segment("the", "star"),
            _segment("the", "moon"),
        ]
        counts = repetition_counts(segments)
        assert counts["the"] == 2
        assert counts["star"] == 1

    def test_repetition_raises_importance(self):
        words = [_segment("alpha"), _segment("alpha"), _segment("alpha")]
        result = apply_emphasis(words)
        assert all(w.importance > 0.0 for w in result[0].words)


class TestScorerRegistry:
    def test_builtin_registered(self):
        assert "rules" in EMPHASIS_REGISTRY

    def test_plugin_scorer(self):
        def constant(words, counts):
            return [0.8] * len(words)

        EMPHASIS_REGISTRY.add("constant-high", constant)
        result = apply_emphasis([_segment("one", "two")], scorer="constant-high")
        assert all(word.emphasis == EmphasisMode.HIGH for word in result[0].words)

    def test_unknown_scorer_raises(self):
        with pytest.raises(KeyError, match="no emphasis registered"):
            apply_emphasis([_segment("one")], scorer="nope")
