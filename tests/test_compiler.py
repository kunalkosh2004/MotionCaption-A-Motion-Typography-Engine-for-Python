import pytest

from motion_caption import (
    DesignSpace,
    PropertyKind,
    Resolution,
)
from motion_caption.compiler import Compiler, compile
from motion_caption.ir import CaptionRequest, SpeakerTrack
from motion_caption.models.geometry import Point
from motion_caption.models.transcript import EmphasisMode, Transcript, WordTimestamp
from motion_caption.themes import THEME_REGISTRY
from motion_caption.themes.spec import EmphasisAppearance, ThemeSpec
from motion_caption.typography.fonts import FontRef, FontStack


def _transcript(text="Hello motion typography"):
    tokens = text.split()
    words = []
    cursor = 0.0
    for token in tokens:
        words.append(WordTimestamp(text=token, start=cursor, end=cursor + 0.8))
        cursor += 1.0
    return Transcript(words=words)


def _theme(any_font) -> ThemeSpec:
    return ThemeSpec(
        name="compiler_test",
        font_stack=FontStack(fonts=[FontRef(family=any_font.family, weight=any_font.weight)]),
        style={
            "size": "48px",
            "fill": {"color": "#FFFFFF"},
            "shadow": {"offset": {"dx": "2px", "dy": "2px"}, "blur": "2px", "opacity": 0.6},
        },
        emphasis={
            EmphasisMode.HIGH: EmphasisAppearance(scale=1.2),
        },
    )


@pytest.fixture
def theme(any_font) -> ThemeSpec:
    return _theme(any_font)


@pytest.fixture
def compiler() -> Compiler:
    return Compiler()


def _request(theme, **overrides) -> CaptionRequest:
    data = {"transcript": _transcript(), "theme": theme}
    data.update(overrides)
    return CaptionRequest(**data)


class TestCompilerPipeline:
    def test_compiles_transcript_to_timeline(self, theme, compiler):
        timeline = compiler.compile(_request(theme))
        assert timeline.tracks
        words = timeline.words
        assert len(words) == 3
        for word in words:
            assert word.box.width > 0
            assert word.typography is not None
            assert word.typography.font_size > 0
            assert word.animation is not None
            assert word.animation.tracks  # at least opacity
        event = timeline.events[0]
        assert event.style is not None
        assert event.style.typography.shadow is not None
        assert event.region.box.height > 0
        assert event.duration > 0

    def test_determinism_byte_identical(self, theme, compiler):
        a = compiler.compile(_request(theme)).model_dump_json()
        b = compiler.compile(_request(theme)).model_dump_json()
        assert a == b

    def test_cache_returns_same_object(self, theme, compiler):
        request = _request(theme)
        assert compiler.compile(request) is compiler.compile(request)

    def test_different_requests_not_cached_together(self, theme, compiler):
        a = compiler.compile(_request(theme))
        b = compiler.compile(_request(theme, metadata={"title": "other"}))
        assert a is not b

    def test_default_compile_function(self, theme):
        timeline = compile(_request(theme))
        assert len(timeline.words) == 3


class TestThemeResolution:
    def test_theme_by_registry_name(self, any_font):
        spec = _theme(any_font)
        THEME_REGISTRY.add("compiler_test", spec, overwrite=True)
        request = CaptionRequest(transcript=_transcript(), theme="compiler_test")
        timeline = compile(request)
        assert timeline.styles[0].name == "compiler_test"
        assert len(timeline.words) == 3

    def test_ai_theme_recommendation_fallback(self, any_font):
        spec = _theme(any_font)
        THEME_REGISTRY.add("compiler_test", spec, overwrite=True)
        request = CaptionRequest(
            transcript=_transcript(),
            theme=None,
            llm_annotations={"theme": "compiler_test"},
        )
        timeline = compile(request)
        assert timeline.styles[0].name == "compiler_test"

    def test_explicit_theme_beats_ai(self, any_font):
        spec = _theme(any_font)
        other = ThemeSpec(
            name="compiler_other",
            font_stack=FontStack(fonts=[FontRef(family=any_font.family, weight=any_font.weight)]),
        )
        THEME_REGISTRY.add("compiler_other", other, overwrite=True)
        THEME_REGISTRY.add("compiler_test", spec, overwrite=True)
        request = CaptionRequest(
            transcript=_transcript(),
            theme="compiler_other",
            llm_annotations={"theme": "compiler_test"},
        )
        assert compile(request).styles[0].name == "compiler_other"


class TestAIContribution:
    def test_ai_splits_override_segmentation(self, theme, compiler):
        transcript = _transcript("one two three four")
        request = _request(
            theme,
            transcript=transcript,
            llm_annotations={"splits": [[0, 1], [2, 3]]},
        )
        timeline = compiler.compile(request)
        assert len(timeline.events) == 2
        assert [len(e.words) for e in timeline.events] == [2, 2]

    def test_ai_importance_override(self, theme, compiler):
        request = _request(theme, llm_annotations={"importance": {0: 0.9}})
        words = compiler.compile(request).words
        assert words[0].importance == pytest.approx(0.9)

    def test_ai_emphasis_override(self, theme, compiler):
        request = _request(theme, llm_annotations={"emphasis": {1: EmphasisMode.HIGH}})
        words = compiler.compile(request).words
        assert words[1].emphasis is EmphasisMode.HIGH
        assert words[1].typography is not None


class TestSpeakers:
    def test_speaker_tracks_tag_events(self, theme, compiler):
        request = _request(
            theme,
            llm_annotations={"splits": [[0], [1, 2]]},
            speaker_tracks=[
                SpeakerTrack(id="s1", word_indices=[0]),
                SpeakerTrack(id="s2", word_indices=[1, 2]),
            ],
        )
        timeline = compiler.compile(request)
        events = timeline.events
        assert len(timeline.tracks) >= 2
        assert {e.speaker for e in events} == {"s1", "s2"}


class TestScaleAndResolution:
    def test_scale_one_for_design_matching_resolution(self, theme, compiler):
        timeline = compiler.compile(_request(theme))
        assert timeline.scale == pytest.approx(1.0)

    def test_scale_two_for_4k_from_1080p_design(self, theme, compiler):
        request = _request(
            theme,
            resolution=Resolution(width=3840, height=2160),
            design=DesignSpace(reference=Resolution(width=1920, height=1080)),
        )
        assert compiler.compile(request).scale == pytest.approx(2.0)


class TestAnimation:
    def test_emphasis_scale_baked_into_scale_track(self, theme, compiler):
        request = _request(theme, llm_annotations={"emphasis": {0: EmphasisMode.HIGH}})
        timeline = compiler.compile(request)
        word = timeline.words[0]
        assert word.emphasis is EmphasisMode.HIGH
        scale_track = word.animation.tracks.get(PropertyKind.SCALE)
        assert scale_track is not None
        assert scale_track.timeline.sample(word.start).x == pytest.approx(1.2)

    def test_karaoke_uses_word_timing(self, theme, compiler):
        request = _request(
            theme,
            options={"animation": {"strategy": "karaoke"}},
        )
        timeline = compiler.compile(request)
        event = timeline.events[0]
        word = event.words[1]
        assert word.start < word.end
        assert word.start != pytest.approx(event.start)
        assert word.animation is not None
        assert word.animation.phases["in"][0] == pytest.approx(word.start)

    def test_word_regions_sample_offsets(self, theme, compiler):
        request = _request(theme, options={"animation": {"strategy": "slide"}})
        timeline = compiler.compile(request)
        word = timeline.words[0]
        region = word.region_at(timeline.start)
        assert region.position == Point(0.0, region.position.y)
        assert region.position.y >= 0.0
