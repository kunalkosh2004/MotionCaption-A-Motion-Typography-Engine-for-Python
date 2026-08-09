"""WhisperX adapter tests — the whisperx SDK is faked, never imported."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from motion_caption.errors import TranscriptionError
from motion_caption.models import Transcript
from motion_caption.video import whisperx as whisperx_module


class _FakeModel:
    def __init__(self, result: dict) -> None:
        self.result = result

    def transcribe(self, audio) -> dict:
        return self.result


class _FakeWhisperX(ModuleType):
    """Stand-in for the whisperx package."""

    def __init__(self) -> None:
        super().__init__("whisperx")
        self.loaded: list[tuple] = []
        self.result: dict = {"segments": []}
        self.raise_on_load: Exception | None = None
        self.raise_on_transcribe: Exception | None = None

    def load_model(self, *args, **kwargs):
        self.loaded.append((args, kwargs))
        if self.raise_on_load is not None:
            raise self.raise_on_load
        return _FakeModel(self.result)

    def load_audio(self, path):
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        return "audio-bytes"


@pytest.fixture(autouse=True)
def _clear_model_cache():
    """The provider caches loaded models module-wide; keep tests isolated."""
    whisperx_module._MODEL_CACHE.clear()


@pytest.fixture
def fake_whisperx(monkeypatch):
    fake = _FakeWhisperX()
    monkeypatch.setitem(sys.modules, "whisperx", fake)
    return fake


@pytest.fixture
def wav(tmp_path) -> Path:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"RIFF fake wav")
    return path


def _word_segments() -> list[dict]:
    return [
        {
            "text": "hello there",
            "start": 0.0,
            "end": 1.0,
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.4, "score": 0.99},
                {"word": "there", "start": 0.4, "end": 1.0, "score": 0.95},
            ],
        }
    ]


def test_missing_whisperx_raises_transcription_error(monkeypatch, wav) -> None:
    # Deterministic regardless of whether whisperx happens to be installed:
    # swap the lazy importer for one that reproduces a missing install, and
    # assert the adapter converts it into the typed, hinted error.
    def _missing_install():
        raise TranscriptionError(
            "WhisperX is not installed",
            hint="pip install 'motion-caption[whisper]' (or pip install whisperx)",
        )

    monkeypatch.setattr(whisperx_module, "_import_whisperx", _missing_install)
    provider = whisperx_module.WhisperXTranscriptProvider()
    with pytest.raises(TranscriptionError, match="not installed") as exc_info:
        provider.transcribe(wav)
    assert "whisper" in (exc_info.value.hint or "")


def test_missing_audio_file_raises(wav) -> None:
    provider = whisperx_module.WhisperXTranscriptProvider()
    with pytest.raises(TranscriptionError, match="does not exist"):
        provider.transcribe("/no/audio.wav")


def test_word_level_extraction(fake_whisperx, wav) -> None:
    fake_whisperx.result = {"language": "en", "segments": _word_segments()}
    provider = whisperx_module.WhisperXTranscriptProvider()
    transcript = provider.transcribe(wav)
    assert isinstance(transcript, Transcript)
    assert [word.text for word in transcript.words] == ["hello", "there"]
    assert transcript.words[0].confidence == pytest.approx(0.99)
    assert transcript.language == "en"
    assert fake_whisperx.loaded[0][1]["language"] is None  # language param passed


def test_model_defaults_from_env(monkeypatch, fake_whisperx, wav) -> None:
    monkeypatch.setenv("WHISPER_MODEL", "large-v2")
    fake_whisperx.result = {"segments": _word_segments()}
    whisperx_module.WhisperXTranscriptProvider().transcribe(wav)
    assert fake_whisperx.loaded[0][0][0] == "large-v2"


def test_segment_fallback_when_no_word_timestamps(fake_whisperx, wav) -> None:
    fake_whisperx.result = {
        "segments": [{"text": "two words", "start": 0.0, "end": 2.0}]
    }
    provider = whisperx_module.WhisperXTranscriptProvider()
    transcript = provider.transcribe(wav)
    assert [word.text for word in transcript.words] == ["two", "words"]
    assert transcript.words[0].start == 0.0
    assert transcript.words[1].end == 2.0


def test_mixed_segments_keep_order(fake_whisperx, wav) -> None:
    fake_whisperx.result = {
        "segments": [
            {"text": "no words here", "start": 0.0, "end": 3.0},
            {
                "text": "worded",
                "start": 3.0,
                "end": 4.0,
                "words": [{"word": "worded", "start": 3.0, "end": 4.0}],
            },
        ]
    }
    transcript = whisperx_module.WhisperXTranscriptProvider().transcribe(wav)
    assert [word.text for word in transcript.words] == ["no", "words", "here", "worded"]


def test_overlapping_words_are_normalized(fake_whisperx, wav) -> None:
    fake_whisperx.result = {
        "segments": [
            {
                "text": "a b",
                "start": 0.0,
                "end": 2.0,
                "words": [
                    {"word": "a", "start": 0.0, "end": 1.5},
                    {"word": "b", "start": 1.2, "end": 2.0},  # overlaps "a"
                ],
            }
        ]
    }
    transcript = whisperx_module.WhisperXTranscriptProvider().transcribe(wav)
    assert transcript.words[0].end == 1.2  # clamped
    assert transcript.words[1].start == 1.2


def test_empty_result_yields_empty_transcript(fake_whisperx, wav) -> None:
    fake_whisperx.result = {"segments": []}
    transcript = whisperx_module.WhisperXTranscriptProvider().transcribe(wav)
    assert transcript.words == []


def test_model_load_failure_raises(fake_whisperx, wav) -> None:
    fake_whisperx.raise_on_load = RuntimeError("CUDA out of memory")
    with pytest.raises(TranscriptionError, match="failed to load"):
        whisperx_module.WhisperXTranscriptProvider().transcribe(wav)


def test_transcribe_failure_raises(fake_whisperx, wav) -> None:
    fake_whisperx.raise_on_transcribe = RuntimeError("boom")
    provider = whisperx_module.WhisperXTranscriptProvider()

    original = fake_whisperx.load_model

    def _load(*args, **kwargs):
        model = original(*args, **kwargs)

        def _transcribe(audio):
            raise RuntimeError("boom")

        model.transcribe = _transcribe
        return model

    fake_whisperx.load_model = _load
    with pytest.raises(TranscriptionError, match="transcription failed"):
        provider.transcribe(wav)


def test_invalid_device_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported device"):
        whisperx_module.WhisperXTranscriptProvider(device="quantum")
