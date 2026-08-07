import pytest

from motion_caption import Segment, Transcript, Word, WordTimestamp


class TestWordTimestamp:
    def test_whisperx_alias(self):
        word = WordTimestamp(word="hello", start=0.1, end=0.3)
        assert word.text == "hello"

    def test_duration(self):
        assert WordTimestamp(text="hi", start=1.0, end=1.5).duration == 0.5

    def test_invalid_timing(self):
        with pytest.raises(ValueError):
            WordTimestamp(text="hi", start=2.0, end=1.0)

    def test_confidence_range(self):
        with pytest.raises(ValueError):
            WordTimestamp(text="hi", start=0.0, end=1.0, confidence=2.0)


class TestTranscript:
    def test_duration_and_text(self):
        transcript = Transcript(
            words=[
                WordTimestamp(text="hello", start=0.0, end=0.5),
                WordTimestamp(text="world", start=0.5, end=1.0),
            ]
        )
        assert transcript.duration == 1.0
        assert transcript.text == "hello world"
        assert transcript.word_count == 2

    def test_empty(self):
        transcript = Transcript()
        assert transcript.duration == 0.0
        assert transcript.text == ""


class TestWordAndSegment:
    def test_word_emphasis_defaults(self):
        word = Word(text="hey", start=0.0, end=0.2)
        assert word.importance == 0.0
        assert word.emphasis.value == "none"

    def test_importance_range(self):
        with pytest.raises(ValueError):
            Word(text="hey", start=0.0, end=0.2, importance=1.5)

    def test_segment_properties(self):
        segment = Segment(
            text="two words",
            start=0.0,
            end=1.0,
            words=[Word(text="two", start=0.0, end=0.4), Word(text="words", start=0.4, end=1.0)],
        )
        assert segment.duration == 1.0
        assert segment.word_count == 2

    def test_segment_bad_timing(self):
        with pytest.raises(ValueError):
            Segment(text="x", start=2.0, end=1.0)
