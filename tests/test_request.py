import pytest

from motion_caption.ir import (
    AIContribution,
    CaptionRequest,
    CompileOptions,
    SpeakerTrack,
)
from motion_caption.models.transcript import EmphasisMode, Transcript, WordTimestamp
from motion_caption.models.units import DesignSpace, Resolution
from motion_caption.themes.spec import ThemeSpec


def _request(**overrides):
    data = {"transcript": Transcript(words=[WordTimestamp(text="hi", start=0.0, end=1.0)])}
    data.update(overrides)
    return CaptionRequest(**data)


class TestCaptionRequestDefaults:
    def test_minimal_request(self):
        request = _request()
        assert request.resolved_resolution == Resolution(width=1920, height=1080)
        assert request.resolved_design == DesignSpace(reference=Resolution(1920, 1080))
        assert request.resolved_options == CompileOptions()

    def test_metadata_and_extensions_pass_through(self):
        request = _request(
            metadata={"title": "demo"}, future_extensions={"brand": {"accent": "#FF0"}}
        )
        assert request.metadata["title"] == "demo"
        assert request.future_extensions["brand"]["accent"] == "#FF0"


class TestTheme:
    def test_theme_name_stays_a_string(self):
        request = _request(theme="clean")
        assert request.theme == "clean"
        assert not isinstance(request.theme, ThemeSpec)

    def test_theme_spec_kept(self):
        spec = ThemeSpec(name="custom")
        request = _request(theme=spec)
        assert isinstance(request.theme, ThemeSpec)
        assert request.theme.name == "custom"


class TestResolution:
    def test_standard_name(self):
        assert _request(resolution="1080p").resolved_resolution == Resolution(1920, 1080)

    def test_wxh_string(self):
        assert _request(resolution="1280x720").resolved_resolution == Resolution(1280, 720)

    def test_resolution_object(self):
        request = _request(resolution=Resolution(width=100, height=200))
        assert request.resolution == Resolution(100, 200)
        assert request.resolved_resolution == Resolution(100, 200)

    def test_invalid_string_rejected(self):
        with pytest.raises(ValueError):
            _request(resolution="not-a-resolution")


class TestSpeakerAndAI:
    def test_speaker_tracks(self):
        request = _request(
            speaker_tracks=[
                SpeakerTrack(id="a", word_indices=[0, 1], bias=0.8),
                SpeakerTrack(id="b", word_indices=[2]),
            ]
        )
        assert request.speaker_tracks[0].bias == 0.8
        assert request.speaker_tracks[1].word_indices == [2]

    def test_llm_annotations(self):
        request = _request(
            llm_annotations=AIContribution(
                importance={0: 0.9},
                emphasis={1: EmphasisMode.HIGH},
                splits=[[0, 1]],
                theme="music_video",
                emotion="energetic",
            )
        )
        assert request.llm_annotations.theme == "music_video"
        assert request.llm_annotations.emphasis[1] is EmphasisMode.HIGH


class TestRequestSerialization:
    def test_roundtrip(self):
        request = _request(theme="clean", resolution="1080p", metadata={"k": "v"})
        restored = CaptionRequest.model_validate_json(request.model_dump_json())
        assert restored == request
