"""Gemini transcript provider tests — the google-genai SDK is faked, never imported."""

from __future__ import annotations

from pathlib import Path

import pytest

from motion_caption.errors import TranscriptionError
from motion_caption.models import Transcript
from motion_caption.video import gemini as gemini_module


class _FakeFile:
    def __init__(self, name: str = "files/audio", state: str = "ACTIVE") -> None:
        self.name = name
        self.state = state


class _FakeClient:
    def __init__(self, genai: _FakeGenAI) -> None:
        self.genai = genai

    @property
    def files(self):
        return self

    @property
    def models(self):
        return self

    def upload(self, file):
        self.genai.uploaded.append(file)
        if self.genai.raise_on_upload is not None:
            raise self.genai.raise_on_upload
        if self.genai.upload_state is not None:
            return _FakeFile(state=self.genai.upload_state)
        return _FakeFile(state="ACTIVE")

    def get(self, name):
        self.genai.got.append(name)
        return _FakeFile(name=name, state="ACTIVE")

    def generate_content(self, *, model, contents, config):
        self.genai.calls.append(
            {"model": model, "contents": contents, "config": config}
        )
        if self.genai.raise_on_generate is not None:
            raise self.genai.raise_on_generate
        response = type("Response", (), {})()
        response.text = self.genai.response_text
        return response


class _FakeGenAI:
    """Stand-in for the google-genai package surface the adapter touches."""

    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.got: list[str] = []
        self.calls: list[dict] = []
        self.response_text = ""
        self.upload_state: str | None = None
        self.raise_on_upload: Exception | None = None
        self.raise_on_generate: Exception | None = None
        self.types = type(
            "Types",
            (),
            {"GenerateContentConfig": lambda **kwargs: kwargs},
        )

    def Client(self, *, api_key):
        self.api_key = api_key
        return _FakeClient(self)


@pytest.fixture
def fake_genai(monkeypatch) -> _FakeGenAI:
    fake = _FakeGenAI()
    monkeypatch.setattr(gemini_module, "_import_genai", lambda: fake)
    return fake


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    path = tmp_path / "audio.wav"
    path.write_bytes(b"RIFF fake wav")
    return path


@pytest.fixture
def provider() -> gemini_module.GeminiTranscriptProvider:
    return gemini_module.GeminiTranscriptProvider(api_key="test-key")


def test_missing_genai_raises_transcription_error(monkeypatch, wav) -> None:
    def _missing_install():
        raise TranscriptionError(
            "google-genai is not installed",
            hint="pip install 'motion-caption[ai]' (or pip install google-genai)",
        )

    monkeypatch.setattr(gemini_module, "_import_genai", _missing_install)
    provider = gemini_module.GeminiTranscriptProvider(api_key="test-key")
    with pytest.raises(TranscriptionError, match="not installed") as exc_info:
        provider.transcribe(wav)
    assert "ai" in (exc_info.value.hint or "")


def test_missing_api_key_raises(monkeypatch, wav) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    provider = gemini_module.GeminiTranscriptProvider()
    with pytest.raises(TranscriptionError, match="no api_key") as exc_info:
        provider.transcribe(wav)
    assert "GEMINI_API_KEY" in (exc_info.value.hint or "")


def test_api_key_falls_back_to_env(monkeypatch, fake_genai, wav) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    gemini_module.GeminiTranscriptProvider().transcribe(wav)
    assert fake_genai.api_key == "env-key"


def test_missing_audio_file_raises(wav) -> None:
    provider = gemini_module.GeminiTranscriptProvider(api_key="test-key")
    with pytest.raises(TranscriptionError, match="does not exist"):
        provider.transcribe("/no/audio.wav")


def test_happy_path_splits_words_evenly(fake_genai, provider, wav) -> None:
    fake_genai.response_text = (
        '{"language": "en", "segments": ['
        '{"start": 0.0, "end": 1.0, "text": "hello there"},'
        '{"start": 1.0, "end": 2.0, "text": "world"}]}'
    )
    transcript = provider.transcribe(wav)
    assert isinstance(transcript, Transcript)
    assert [word.text for word in transcript.words] == ["hello", "there", "world"]
    assert transcript.language == "en"
    assert transcript.words[0].start == 0.0
    assert transcript.words[0].end == 0.5
    assert transcript.words[1].start == 0.5
    assert transcript.words[2].end == 2.0
    # The audio file was uploaded and the prompt/model/config were passed.
    assert fake_genai.uploaded == [str(wav)]
    call = fake_genai.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["config"]["response_mime_type"] == "application/json"
    assert "segments" in call["contents"][-1]


def test_theme_recommendation_is_parsed(fake_genai, provider, wav) -> None:
    fake_genai.response_text = (
        '{"language": "pa", "theme": "Sport", "segments": ['
        '{"start": 0.0, "end": 1.0, "text": "hello world"}]}'
    )
    transcript = provider.transcribe(wav)
    assert transcript.theme == "sport"


def test_invalid_theme_recommendation_is_dropped(fake_genai, provider, wav) -> None:
    fake_genai.response_text = (
        '{"language": "en", "theme": "neon-cyber", "segments": ['
        '{"start": 0.0, "end": 1.0, "text": "hello"}]}'
    )
    assert provider.transcribe(wav).theme is None


def test_missing_theme_recommendation_is_none(fake_genai, provider, wav) -> None:
    fake_genai.response_text = '{"language": "en", "segments": []}'
    assert provider.transcribe(wav).theme is None


def test_model_defaults_from_env(monkeypatch, fake_genai, wav) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.0-flash")
    fake_genai.response_text = '{"segments": []}'
    gemini_module.GeminiTranscriptProvider().transcribe(wav)
    assert fake_genai.calls[0]["model"] == "gemini-2.5-flash"  # constructor default wins


def test_fenced_json_is_tolerated(fake_genai, provider, wav) -> None:
    fake_genai.response_text = (
        '```json\n{"segments": [{"start": 0.0, "end": 1.0, "text": "one two"}]}\n```'
    )
    transcript = provider.transcribe(wav)
    assert [word.text for word in transcript.words] == ["one", "two"]


def test_per_word_timestamps_are_preferred(fake_genai, provider, wav) -> None:
    fake_genai.response_text = (
        '{"segments": [{"start": 0.0, "end": 2.0, "text": "a b", '
        '"words": [{"text": "a", "start": 0.0, "end": 0.3}, '
        '{"text": "b", "start": 0.3, "end": 2.0}]}]}'
    )
    transcript = provider.transcribe(wav)
    assert [word.text for word in transcript.words] == ["a", "b"]
    assert transcript.words[0].end == 0.3
    assert transcript.words[1].start == 0.3


def test_top_level_words_are_tolerated(fake_genai, provider, wav) -> None:
    fake_genai.response_text = (
        '{"words": [{"text": "x", "start": 0.0, "end": 0.5}, '
        '{"text": "y", "start": 0.5, "end": 1.0}]}'
    )
    transcript = provider.transcribe(wav)
    assert [word.text for word in transcript.words] == ["x", "y"]


def test_overlapping_or_bad_segments_normalized(fake_genai, provider, wav) -> None:
    fake_genai.response_text = (
        '{"segments": ['
        '{"start": 0.0, "end": 2.0, "text": "a b"},'
        '{"start": 1.5, "end": 3.0, "text": "c"},'
        '{"start": -1.0, "end": 5.0, "text": "dropped"},'
        '{"start": 5.0, "end": 2.0, "text": "also dropped"},'
        '{"text": "no timing"}]}'
    )
    transcript = provider.transcribe(wav)
    assert [word.text for word in transcript.words] == ["a", "b", "c"]
    assert transcript.words[1].end == 1.5  # clamped to the next word


def test_empty_response_yields_empty_transcript(fake_genai, provider, wav) -> None:
    fake_genai.response_text = ""
    assert provider.transcribe(wav).words == []


def test_invalid_json_raises(fake_genai, provider, wav) -> None:
    fake_genai.response_text = "not json"
    with pytest.raises(TranscriptionError, match="transcription failed"):
        provider.transcribe(wav)


def test_upload_failure_raises(fake_genai, provider, wav) -> None:
    fake_genai.raise_on_upload = RuntimeError("403 permission denied")
    with pytest.raises(TranscriptionError, match="upload failed"):
        provider.transcribe(wav)


def test_generate_failure_raises(fake_genai, provider, wav) -> None:
    fake_genai.raise_on_generate = RuntimeError("quota exceeded")
    with pytest.raises(TranscriptionError, match="transcription failed"):
        provider.transcribe(wav)


def test_rejected_file_state_raises(fake_genai, provider, wav) -> None:
    fake_genai.upload_state = "FAILED"
    with pytest.raises(TranscriptionError, match="rejected"):
        provider.transcribe(wav)


def test_processes_audio_until_active(fake_genai, provider, wav) -> None:
    fake_genai.upload_state = "PROCESSING"
    fake_genai.response_text = '{"segments": [{"start": 0.0, "end": 0.5, "text": "hi"}]}'
    transcript = provider.transcribe(wav)
    assert fake_genai.got  # polled files.get until ACTIVE
    assert [word.text for word in transcript.words] == ["hi"]


class _FakeFFmpeg:
    """Injected stand-in so chunking never touches the real ffmpeg."""

    def __init__(self, duration: float = 100.0) -> None:
        self.duration_value = duration
        self.split_calls: list[tuple] = []

    def duration(self, _path) -> float:
        return self.duration_value

    def split_audio(self, _path, output_dir, **kwargs) -> list[Path]:
        self.split_calls.append((output_dir, kwargs))
        return [output_dir / "c0.wav", output_dir / "c1.wav"]


def _chunk_payload(
    chunk: str, *, start: float = 0.0, end: float = 2.0, theme: str | None = None
) -> str:
    theme_json = f'"theme": "{theme}", ' if theme else ""
    return (
        '{"language": "en", '
        f"{theme_json}"
        f'"segments": [{{"start": {start}, "end": {end}, "text": "{chunk} one two"}}]}}'
    )


def test_long_audio_is_chunked_and_merged(fake_genai, monkeypatch, wav) -> None:
    ffmpeg = _FakeFFmpeg(duration=100.0)
    transcribe_calls: list[tuple] = []

    def _fake_call(genai, api_key, model, path, timeout):
        transcribe_calls.append((model, Path(path).name))
        if Path(path).name == "c1.wav":
            return _chunk_payload("chunk1", start=4.0, end=6.0)
        return _chunk_payload("chunk0", theme="sport")

    monkeypatch.setattr(gemini_module, "_call_gemini", _fake_call)
    provider = gemini_module.GeminiTranscriptProvider(api_key="test-key", ffmpeg=ffmpeg)
    transcript = provider.transcribe(wav)

    assert len(ffmpeg.split_calls) == 1
    split_dir, kwargs = ffmpeg.split_calls[0]
    assert kwargs == {"chunk_seconds": 45.0, "overlap_seconds": 3.0}
    assert split_dir.name.startswith("motioncaption-chunks-")
    assert transcribe_calls == [
        ("gemini-2.5-flash", "c0.wav"),
        ("gemini-2.5-flash", "c1.wav"),
    ]
    # chunk0 words at 0..; chunk1 words offset by 42s with the overlap head dropped.
    assert [word.text for word in transcript.words] == [
        "chunk0", "one", "two", "chunk1", "one", "two",
    ]
    assert transcript.words[0].start == 0.0
    assert transcript.words[3].start == pytest.approx(42.0 + 4.0)
    assert transcript.theme == "sport"


def test_short_audio_transcribes_single_call(fake_genai, monkeypatch, wav) -> None:
    ffmpeg = _FakeFFmpeg(duration=30.0)
    monkeypatch.setattr(
        gemini_module, "_call_gemini", lambda *args: _chunk_payload("short", theme="clean")
    )
    provider = gemini_module.GeminiTranscriptProvider(api_key="test-key", ffmpeg=ffmpeg)
    transcript = provider.transcribe(wav)
    assert ffmpeg.split_calls == []
    assert [word.text for word in transcript.words] == ["short", "one", "two"]
    assert transcript.theme == "clean"


def test_unprobeable_audio_falls_back_to_single_call(fake_genai, monkeypatch, wav) -> None:
    class _BrokeFFmpeg(_FakeFFmpeg):
        def duration(self, _path) -> float:
            from motion_caption.errors import FFmpegError

            raise FFmpegError("no ffmpeg", hint="install ffmpeg")

    monkeypatch.setattr(
        gemini_module, "_call_gemini", lambda *args: _chunk_payload("fallback")
    )
    provider = gemini_module.GeminiTranscriptProvider(
        api_key="test-key", ffmpeg=_BrokeFFmpeg()
    )
    transcript = provider.transcribe(wav)
    assert [word.text for word in transcript.words] == ["fallback", "one", "two"]


def test_chunking_can_be_disabled(fake_genai, monkeypatch, wav) -> None:
    ffmpeg = _FakeFFmpeg(duration=200.0)
    monkeypatch.setattr(
        gemini_module, "_call_gemini", lambda *args: _chunk_payload("whole")
    )
    provider = gemini_module.GeminiTranscriptProvider(
        api_key="test-key", ffmpeg=ffmpeg, chunk_seconds=None
    )
    transcript = provider.transcribe(wav)
    assert ffmpeg.split_calls == []
    assert [word.text for word in transcript.words] == ["whole", "one", "two"]


def test_merge_chunk_transcripts_discards_overlap_tail(fake_genai, wav) -> None:
    first = gemini_module._parse_transcript(
        '{"segments": [{"start": 0.0, "end": 2.0, "text": "a b"}, '
        '{"start": 2.0, "end": 4.0, "text": "c"}]}'
    )
    second = gemini_module._parse_transcript(
        '{"segments": [{"start": 0.0, "end": 1.0, "text": "b again"}, '
        '{"start": 2.0, "end": 4.0, "text": "d e"}]}'
    )
    merged = gemini_module._merge_chunk_transcripts(
        [first, second], chunk_seconds=10.0, overlap_seconds=2.0
    )
    # Chunk 1 covers [8, 18); words starting before 2s local (the re-transcribed
    # head, "b again") are dropped, and the rest are offset by 8s.
    assert [word.text for word in merged.words] == ["a", "b", "c", "d", "e"]
    assert merged.words[3].start == 10.0
    assert merged.words[4].start == 11.0
    assert merged.theme is None


def test_merge_chunk_transcripts_empty_and_theme(fake_genai, wav) -> None:
    empty = gemini_module._merge_chunk_transcripts([], chunk_seconds=10.0, overlap_seconds=2.0)
    assert empty.words == []
    themed = gemini_module._parse_transcript('{"language": "pa", "theme": "Sport", "segments": []}')
    merged = gemini_module._merge_chunk_transcripts(
        [themed, gemini_module._parse_transcript('{"segments": []}')],
        chunk_seconds=10.0,
        overlap_seconds=2.0,
    )
    assert merged.theme == "sport"
    assert merged.language == "pa"
