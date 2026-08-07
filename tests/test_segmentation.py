import pytest

from motion_caption import (
    Segment,
    SegmentationConfig,
    Segmenter,
    Transcript,
    WordTimestamp,
    segment_transcript,
)
from motion_caption.segmentation import (
    SEGMENTATION_REGISTRY,
    break_priority,
    pause_priority,
    reading_speed,
)
from motion_caption.segmentation.rules import (
    CLAUSE_BREAK,
    CONJUNCTION_BREAK,
    DEFAULT_BREAK,
    NO_BREAK,
    SENTENCE_BREAK,
)


def _timed(items, gap=0.1):
    """items: sequence of (text, duration) or (text, duration, gap_after)."""
    words = []
    t = 0.0
    for item in items:
        text, duration = item[0], item[1]
        after = item[2] if len(item) > 2 else gap
        words.append(WordTimestamp(text=text, start=t, end=t + duration))
        t = t + duration + after
    return Transcript(words=words)


class TestBreakRules:
    def test_sentence_punctuation(self):
        assert break_priority("home.", "She") == SENTENCE_BREAK
        assert break_priority("what?", "Next") == SENTENCE_BREAK

    def test_clause_punctuation(self):
        assert break_priority("met,", "John") == CLAUSE_BREAK

    def test_conjunction(self):
        assert break_priority("home", "and") == CONJUNCTION_BREAK

    def test_article_no_break(self):
        assert break_priority("went", "the") == NO_BREAK
        assert break_priority("at", "a") == NO_BREAK

    def test_default_boundary(self):
        assert break_priority("went", "home") == DEFAULT_BREAK

    def test_non_english_defaults(self):
        assert break_priority("hola", "que", language="fr") == DEFAULT_BREAK
        assert break_priority("chez", "le", language="fr") == DEFAULT_BREAK

    def test_pause_priority(self):
        assert pause_priority(2.0, 0.35) == SENTENCE_BREAK
        assert pause_priority(0.05, 0.35) == DEFAULT_BREAK


class TestSentenceStrategy:
    def test_sentence_split_within_caps(self):
        transcript = _timed(
            [("I", 0.5), ("went", 0.5), ("home.", 0.5), ("She", 0.5), ("stayed.", 0.5)]
        )
        segments = segment_transcript(transcript)
        assert [s.text for s in segments] == ["I went home.", "She stayed."]

    def test_clause_split(self):
        transcript = _timed([("We", 0.5), ("met,", 0.5), ("John", 0.5), ("left.", 0.5)])
        segments = segment_transcript(transcript)
        assert [s.text for s in segments] == ["We met,", "John left."]

    def test_no_split_when_fits_with_weak_breaks(self):
        transcript = _timed([("a", 0.5)] * 6)
        segments = segment_transcript(transcript)
        assert len(segments) == 1
        assert segments[0].text == "a a a a a a"

    def test_max_words_cap(self):
        transcript = _timed([("w", 0.5)] * 10)
        config = SegmentationConfig(max_words=4, target_words=4)
        segments = segment_transcript(transcript, config)
        assert [s.word_count for s in segments] == [4, 4, 2]

    def test_cap_respects_priority(self):
        transcript = _timed(
            [
                ("a", 0.5), ("b", 0.5), ("c", 0.5), ("and", 0.5),
                ("d", 0.5), ("e", 0.5), ("f", 0.5),
            ]
        )
        config = SegmentationConfig(max_words=5, target_words=5)
        segments = segment_transcript(transcript, config)
        assert [s.text for s in segments] == ["a b c", "and d e f"]

    def test_pause_split(self):
        transcript = _timed(
            [("one", 0.5), ("two", 0.5, 2.0), ("three", 0.5), ("four", 0.5)]
        )
        segments = segment_transcript(transcript)
        assert [s.text for s in segments] == ["one two", "three four"]

    def test_max_duration_cap(self):
        transcript = _timed([("w", 1.0)] * 4)
        config = SegmentationConfig(max_words=10, max_duration=2.5)
        segments = segment_transcript(transcript, config)
        assert len(segments) == 2

    def test_min_duration_merges_tail(self):
        transcript = _timed(
            [("a", 1.0), ("b", 1.0), ("c.", 1.0), ("d", 0.1)]
        )
        config = SegmentationConfig(max_words=6, min_duration=0.5)
        segments = segment_transcript(transcript, config)
        assert len(segments) == 1
        assert segments[0].text == "a b c. d"

    def test_empty_transcript(self):
        assert segment_transcript(Transcript()) == []

    def test_single_word(self):
        transcript = _timed([("hello", 0.5)])
        segments = segment_transcript(transcript)
        assert len(segments) == 1
        assert segments[0].text == "hello"
        assert segments[0].start == 0.0
        assert segments[0].end == 0.5

    def test_coverage_invariant(self):
        texts = [
            "one", "two", "three.", "four", "five",
            "six", "seven", "and", "eight", "nine,", "ten.",
        ]
        transcript = _timed([(text, 0.4) for text in texts])
        segments = segment_transcript(transcript, SegmentationConfig(max_words=4))
        assert " ".join(s.text for s in segments) == transcript.text
        assert sum(s.word_count for s in segments) == len(texts)
        assert segments[0].start == 0.0
        assert segments[-1].end == transcript.words[-1].end
        for previous, following in zip(segments[:-1], segments[1:], strict=True):
            assert previous.words[-1].end <= following.words[0].start

    def test_language_from_transcript_when_config_none(self):
        transcript = _timed([("uno", 0.5), ("dos", 0.5)])
        transcript.language = "es"
        segments = segment_transcript(transcript)
        assert len(segments) == 1


class TestStrategies:
    def test_strict_caps_only(self):
        transcript = _timed([("w", 0.5)] * 7)
        config = SegmentationConfig(max_words=3)
        segments = segment_transcript(transcript, config, strategy="strict")
        assert [s.word_count for s in segments] == [3, 3, 1]

    def test_pauses_ignores_grammar(self):
        transcript = _timed(
            [("one", 0.5), ("two,", 0.5, 2.0), ("three", 0.5)]
        )
        segments = segment_transcript(transcript, strategy="pauses")
        assert [s.text for s in segments] == ["one two,", "three"]

    def test_unknown_strategy_raises(self):
        with pytest.raises(KeyError, match="no segmentation registered"):
            segment_transcript(_timed([("a", 0.5)]), strategy="nope")

    def test_plugin_strategy(self):
        def one_per_word(transcript, config):
            return [
                Segment(text=word.text, start=word.start, end=word.end)
                for word in transcript.words
            ]

        SEGMENTATION_REGISTRY.add("one-per-word", one_per_word)
        transcript = _timed([("a", 0.2), ("b", 0.2), ("c", 0.2)])
        segments = segment_transcript(transcript, strategy="one-per-word")
        assert [s.text for s in segments] == ["a", "b", "c"]


class TestSegmenter:
    def test_facade_defaults(self):
        transcript = _timed([("a", 0.5), ("b.", 0.5)])
        segmenter = Segmenter()
        assert [s.text for s in segmenter.segment(transcript)] == ["a b."]

    def test_facade_custom_strategy(self):
        transcript = _timed([("a", 0.5)] * 5)
        segmenter = Segmenter(SegmentationConfig(max_words=2), strategy="strict")
        assert [s.word_count for s in segmenter.segment(transcript)] == [2, 2, 1]


class TestReadingSpeed:
    def test_words_per_second(self):
        segment = Segment(text="a b c", start=0.0, end=3.0)
        assert reading_speed(segment) == pytest.approx(1.0)

    def test_empty(self):
        assert reading_speed([]) == 0.0

    def test_zero_duration_guard(self):
        segment = Segment(text="a", start=1.0, end=1.0)
        assert reading_speed(segment) == 0.0


class TestConfig:
    def test_target_words_clamped_to_max(self):
        assert SegmentationConfig(max_words=4).target_words == 4

    def test_defaults(self):
        config = SegmentationConfig()
        assert config.max_words == 6
        assert config.max_duration == 7.0
        assert config.language == "en"
