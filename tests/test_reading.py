import pytest

from motion_caption import Segment, Word, adjust_segments, analyze, difficulty_of


def _segment(texts, start=0.0, end=1.0):
    words = [Word(text=text, start=start + i, end=start + i + 0.5) for i, text in enumerate(texts)]
    return Segment(text=" ".join(texts), start=start, end=end, words=words)


class TestDifficulty:
    def test_short_words_easy(self):
        assert difficulty_of("hi there") < difficulty_of("antidisestablishmentarianism")

    def test_empty_is_zero(self):
        assert difficulty_of("") == 0.0

    def test_in_range(self):
        assert 0.0 <= difficulty_of("The quick brown fox jumps over the lazy dog again") <= 1.0


class TestAnalyze:
    def test_words_per_second(self):
        segment = Segment(text="a b c", start=0.0, end=3.0)
        stats = analyze(segment)
        assert stats.words_per_second == pytest.approx(1.0)
        assert stats.word_count == 3

    def test_density_relative_to_target(self):
        segment = Segment(text="a b c", start=0.0, end=3.0)
        stats = analyze(segment, target_wps=2.0)
        assert stats.density == pytest.approx(0.5)

    def test_uses_spoken_duration_from_words(self):
        segment = Segment(
            text="a b",
            start=0.0,
            end=10.0,
            words=[Word(text="a", start=0, end=1), Word(text="b", start=1, end=2)],
        )
        stats = analyze(segment)
        assert stats.duration == pytest.approx(2.0)

    def test_needed_duration(self):
        segment = Segment(text="a b c d", start=0.0, end=1.0)
        stats = analyze(segment, target_wps=2.0)
        assert stats.needed_duration == pytest.approx(2.0)


class TestAdjustSegments:
    def test_extends_short_caption(self):
        segments = [
            _segment(["a", "b", "c", "d", "e"], start=0.0, end=1.0),
            _segment(["next"], start=10.0, end=10.5),
        ]
        adjusted = adjust_segments(segments, target_wps=2.2)
        # 5 words need ~2.27s, but capped at next.start = 10s
        assert adjusted[0].end == pytest.approx(2.2727, abs=0.01)

    def test_capped_by_next_start(self):
        segments = [
            _segment(["a", "b", "c", "d", "e"], start=0.0, end=1.0),
            _segment(["next"], start=1.5, end=2.0),
        ]
        adjusted = adjust_segments(segments, target_wps=2.2)
        assert adjusted[0].end == pytest.approx(1.5)

    def test_no_overlap(self):
        segments = [
            _segment(["one", "two", "three"], start=0.0, end=0.5),
            _segment(["four", "five", "six"], start=3.0, end=3.5),
            _segment(["seven", "eight"], start=6.0, end=6.5),
        ]
        adjusted = adjust_segments(segments)
        for previous, following in zip(adjusted[:-1], adjusted[1:], strict=True):
            assert previous.end <= following.start

    def test_last_segment_extends_freely(self):
        segments = [_segment(["a", "b", "c", "d", "e", "f"], start=0.0, end=1.0)]
        adjusted = adjust_segments(segments, target_wps=2.2)
        assert adjusted[0].end == pytest.approx(6 / 2.2, abs=0.01)

    def test_never_shrinks(self):
        segments = [_segment(["a"], start=0.0, end=5.0)]
        adjusted = adjust_segments(segments)
        assert adjusted[0].end >= 5.0

    def test_empty(self):
        assert adjust_segments([]) == []
