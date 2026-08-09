"""Application error hierarchy tests."""

from __future__ import annotations

import pytest

from motion_caption import (
    AIProviderError,
    ExportError,
    FFmpegError,
    InvalidTranscriptError,
    InvalidVideoError,
    MotionCaptionError,
    PluginError,
    TranscriptionError,
)
from motion_caption.ai.providers import GeminiProvider, OpenAIProvider

ALL_ERRORS = [
    MotionCaptionError,
    InvalidTranscriptError,
    TranscriptionError,
    AIProviderError,
    FFmpegError,
    InvalidVideoError,
    ExportError,
    PluginError,
]


@pytest.mark.parametrize("error_type", ALL_ERRORS)
def test_every_error_is_catchable_as_base(error_type: type[Exception]) -> None:
    assert issubclass(error_type, MotionCaptionError)


def test_hierarchy_relationships() -> None:
    # Invalid video is a specific kind of FFmpeg failure.
    assert issubclass(InvalidVideoError, FFmpegError)
    # AIProviderError keeps the historical RuntimeError contract.
    assert issubclass(AIProviderError, RuntimeError)


def test_message_and_hint_rendering() -> None:
    error = InvalidTranscriptError(
        "transcript has no words", hint="provide a non-empty transcript"
    )
    assert error.message == "transcript has no words"
    assert error.hint == "provide a non-empty transcript"
    assert "transcript has no words" in str(error)
    assert "provide a non-empty transcript" in str(error)


def test_no_hint_renders_plain_message() -> None:
    error = ExportError("exporter crashed")
    assert error.hint is None
    assert str(error) == "exporter crashed"


def test_errors_are_programmatically_catchable() -> None:
    with pytest.raises(FFmpegError):
        raise InvalidVideoError("not a video", hint="check the file with ffprobe")


@pytest.mark.parametrize(
    ("error_type", "message"),
    [
        (InvalidTranscriptError, "empty transcript"),
        (TranscriptionError, "provider failed"),
        (AIProviderError, "bad key"),
        (FFmpegError, "ffmpeg missing"),
        (ExportError, "write failed"),
        (PluginError, "cannot load plugin"),
    ],
)
def test_each_error_carries_its_message(
    error_type: type[MotionCaptionError], message: str
) -> None:
    with pytest.raises(error_type) as exc_info:
        raise error_type(message)
    assert exc_info.value.message == message


def test_ai_providers_raise_ai_provider_error_without_key(monkeypatch) -> None:
    from motion_caption import CaptionRequest, Transcript, WordTimestamp

    request = CaptionRequest(
        transcript=Transcript(
            words=[WordTimestamp(text="hello", start=0.0, end=0.5)]
        )
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for provider in (GeminiProvider(), OpenAIProvider()):
        with pytest.raises(AIProviderError) as exc_info:
            provider.annotate(request)
        assert exc_info.value.hint
