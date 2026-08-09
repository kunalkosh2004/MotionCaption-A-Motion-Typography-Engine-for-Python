"""CaptionVideoPipeline tests — fake ffmpeg, deterministic transcript, no network."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path

import pytest

from motion_caption.compiler.engine import Compiler
from motion_caption.errors import AIProviderError, InvalidTranscriptError
from motion_caption.ir.request import AIContribution, CaptionRequest
from motion_caption.models import Transcript
from motion_caption.video import pipeline as pipeline_module
from motion_caption.video.ffmpeg import VideoMetadata
from motion_caption.video.pipeline import CaptionVideoPipeline, PipelineResult
from motion_caption.video.transcript import FakeTranscriptProvider


class FakeFFmpeg:
    """Records every call; writes small dummy artifacts so outputs exist."""

    def __init__(
        self,
        *,
        resolution: tuple[int, int] = (640, 360),
        duration: float = 1.0,
        has_audio: bool = True,
    ) -> None:
        self.calls: list[tuple] = []
        self.metadata = VideoMetadata(
            path=Path("input.mp4"),
            width=resolution[0],
            height=resolution[1],
            fps=30.0,
            duration=duration,
            has_audio=has_audio,
            has_video=True,
            video_codec="h264",
            audio_codec="aac" if has_audio else None,
        )

    def probe(self, video) -> VideoMetadata:
        self.calls.append(("probe", str(video)))
        return self.metadata

    def extract_audio(self, video, output=None, **kwargs) -> Path:
        self.calls.append(("extract_audio", str(video)))
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"RIFF-wav")
        return target

    def render_frames_to_video(self, frames_dir, fps, output, **kwargs) -> Path:
        self.calls.append(("render_frames_to_video", str(frames_dir), fps, str(output)))
        self.frames_encoded = len(list(Path(frames_dir).glob("*.png")))
        target = Path(output)
        target.write_bytes(b"captioned-mp4")
        return target

    def mux_audio(self, video, audio, output) -> Path:
        self.calls.append(("mux_audio", str(video), str(audio), str(output)))
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"final-mp4")
        return target

    def extract_frame(self, video, time, output) -> Path:
        self.calls.append(("extract_frame", str(video), time))
        target = Path(output)
        from PIL import Image

        Image.new("RGB", (16, 16), (5, 5, 5)).save(target, format="PNG")
        return target


class RecordingCompiler(Compiler):
    """Records every request and compiles for real (deterministic)."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[CaptionRequest] = []

    def compile(self, request: CaptionRequest):
        self.requests.append(request)
        return super().compile(request)


@pytest.fixture
def fake_ffmpeg() -> FakeFFmpeg:
    return FakeFFmpeg()


@pytest.fixture
def compiler() -> RecordingCompiler:
    return RecordingCompiler()


def _transcript(text: str = "hello world") -> Transcript:
    return FakeTranscriptProvider(text, per_word=0.45).transcribe("x.wav")


def test_end_to_end_happy_path(fake_ffmpeg, compiler, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    output = tmp_path / "out" / "captioned.mp4"

    pipeline = CaptionVideoPipeline(
        theme="clean",
        resolution=(640, 360),
        transcript_provider=FakeTranscriptProvider("hello caption world"),
        ffmpeg=fake_ffmpeg,
        compiler=compiler,
        fps=10,
    )
    result = pipeline.process(input_video, output)

    assert isinstance(result, PipelineResult)
    assert result.output_video == output
    assert output.read_bytes() == b"final-mp4"  # muxed output written
    assert result.event_count >= 1
    assert result.word_count == 3
    assert result.frames_rendered > 0
    assert not result.llm_annotated
    assert result.theme == "clean"

    # Operation order: probe → extract_audio → encode → mux.
    kinds = [call[0] for call in fake_ffmpeg.calls]
    assert kinds[0] == "probe"
    assert "extract_audio" in kinds
    assert kinds.index("render_frames_to_video") < kinds.index("mux_audio")

    # The compiler saw one request, resolution defaulted to the input size.
    assert len(compiler.requests) == 1
    assert (compiler.requests[0].resolution.width, compiler.requests[0].resolution.height) == (
        640,
        360,
    )
    assert compiler.requests[0].platform is None
    assert compiler.requests[0].llm_annotations is None

    # Frames were streamed to disk (never held in memory): the encoder saw
    # exactly as many PNGs as the pipeline claims to have rendered.
    assert fake_ffmpeg.frames_encoded == result.frames_rendered > 0


def test_input_missing_raises_invalid_video(tmp_path) -> None:
    pipeline = CaptionVideoPipeline(transcript_provider=FakeTranscriptProvider("x"))
    with pytest.raises(Exception) as exc_info:
        pipeline.process(tmp_path / "missing.mp4")
    from motion_caption.errors import InvalidVideoError

    assert isinstance(exc_info.value, InvalidVideoError)


def test_no_transcript_source_raises(fake_ffmpeg, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    pipeline = CaptionVideoPipeline(ffmpeg=fake_ffmpeg)
    with pytest.raises(InvalidTranscriptError, match="no transcript source"):
        pipeline.process(input_video)


def test_empty_transcript_raises_with_hint(fake_ffmpeg, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    pipeline = CaptionVideoPipeline(
        transcript_provider=FakeTranscriptProvider("   "), ffmpeg=fake_ffmpeg
    )
    with pytest.raises(InvalidTranscriptError, match="no words"):
        pipeline.process(input_video)


def test_explicit_transcript_skips_audio_extraction(fake_ffmpeg, compiler, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    pipeline = CaptionVideoPipeline(
        theme="clean", ffmpeg=fake_ffmpeg, compiler=compiler, fps=10
    )
    pipeline.process(input_video, transcript=_transcript("give me words"))
    assert all(call[0] != "extract_audio" for call in fake_ffmpeg.calls)


class _FakeAIProvider:
    """Records the request; returns a canned contribution (no network)."""

    name = "fake-ai"

    def __init__(self) -> None:
        self.calls: list[CaptionRequest] = []

    def annotate(self, request: CaptionRequest) -> AIContribution:
        self.calls.append(request)
        return AIContribution(importance={0: 0.9}, emotion="informative")


def test_ai_annotate_when_provider_injected(fake_ffmpeg, compiler, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    provider = _FakeAIProvider()
    pipeline = CaptionVideoPipeline(
        theme="clean",
        transcript_provider=FakeTranscriptProvider("ai words here"),
        ai_provider=provider,
        ffmpeg=fake_ffmpeg,
        compiler=compiler,
        fps=10,
    )
    result = pipeline.process(input_video)
    assert result.llm_annotated
    assert len(provider.calls) == 1
    # The compiled request carried the AI contribution.
    assert compiler.requests[0].llm_annotations is not None
    assert compiler.requests[0].llm_annotations.importance == {0: 0.9}


def test_ai_provider_unknown_name_raises(fake_ffmpeg, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    pipeline = CaptionVideoPipeline(
        transcript_provider=FakeTranscriptProvider("x"),
        ai_provider="no-such-provider",
        ffmpeg=fake_ffmpeg,
    )
    with pytest.raises(AIProviderError, match="unknown AI provider"):
        pipeline.process(input_video)


def test_ai_name_resolves_via_registry(monkeypatch, fake_ffmpeg, compiler, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")

    class _StubRegistry:
        def __init__(self, providers: dict) -> None:
            self._providers = providers

        def __contains__(self, key: str) -> bool:
            return key in self._providers

        def __getitem__(self, key: str):
            return self._providers[key]

        @property
        def keys(self):
            return self._providers.keys()

    monkeypatch.setattr(
        pipeline_module,
        "AI_REGISTRY",
        _StubRegistry({"gemini": _FakeAIProvider()}),
    )
    pipeline = CaptionVideoPipeline(
        transcript_provider=FakeTranscriptProvider("registry words"),
        ai_provider="gemini",
        ffmpeg=fake_ffmpeg,
        compiler=compiler,
        fps=10,
    )
    result = pipeline.process(input_video)
    assert result.llm_annotated
    assert compiler.requests[0].llm_annotations is not None


class _ExplodingAI:
    def annotate(self, request: CaptionRequest) -> AIContribution:
        raise RuntimeError("rate limited")


def test_ai_failure_wrapped_in_ai_provider_error(fake_ffmpeg, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    pipeline = CaptionVideoPipeline(
        transcript_provider=FakeTranscriptProvider("x"),
        ai_provider=_ExplodingAI(),
        ffmpeg=fake_ffmpeg,
    )
    with pytest.raises(AIProviderError, match="AI annotation failed") as exc_info:
        pipeline.process(input_video)
    assert "skip" in (exc_info.value.hint or "")


def test_no_audio_source_copies_video(fake_ffmpeg, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    silent = FakeFFmpeg(has_audio=False)
    pipeline = CaptionVideoPipeline(
        transcript_provider=FakeTranscriptProvider("hello world"),
        ffmpeg=silent,
        fps=10,
    )
    output = tmp_path / "out.mp4"
    result = pipeline.process(input_video, output)
    assert output.exists()
    assert "mux_audio" not in [call[0] for call in silent.calls]
    assert result.metadata.has_audio is False


def test_workspace_is_cleaned_up(fake_ffmpeg, compiler, tmp_path) -> None:
    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    workspace = tmp_path / "job-workspace"

    @contextmanager
    def _known_workspace():
        workspace.mkdir()
        try:
            yield workspace
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    monkeypatch_owner = pytest.MonkeyPatch()
    monkeypatch_owner.setattr(pipeline_module, "temporary_directory", _known_workspace)
    try:
        pipeline = CaptionVideoPipeline(
            theme="clean",
            transcript_provider=FakeTranscriptProvider("hello world"),
            ffmpeg=fake_ffmpeg,
            compiler=compiler,
            fps=10,
        )
        result = pipeline.process(input_video, tmp_path / "out.mp4")
    finally:
        monkeypatch_owner.undo()

    assert result.output_video.exists()
    assert not workspace.exists(), "intermediate workspace must be removed"


def test_faces_pass_through(fake_ffmpeg, compiler, tmp_path) -> None:
    from motion_caption.models import Box
    from motion_caption.placement import Face

    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    face = Face(box=Box(100.0, 50.0, 300.0, 350.0))
    pipeline = CaptionVideoPipeline(
        theme="clean",
        transcript_provider=FakeTranscriptProvider("hello world"),
        ffmpeg=fake_ffmpeg,
        compiler=compiler,
        fps=10,
    )
    pipeline.process(input_video, faces=[face])
    assert compiler.requests[0].faces == [face]


def test_face_detector_populates_request(fake_ffmpeg, compiler, tmp_path) -> None:
    from motion_caption.models import Box

    class _Detector:
        def detect(self, frame):
            return [Box(5.0, 5.0, 55.0, 55.0)]

    input_video = tmp_path / "clip.mp4"
    input_video.write_bytes(b"input")
    pipeline = CaptionVideoPipeline(
        theme="clean",
        transcript_provider=FakeTranscriptProvider("hello world"),
        face_detector=_Detector(),
        ffmpeg=fake_ffmpeg,
        compiler=compiler,
        fps=10,
    )
    pipeline.process(input_video)
    assert len(compiler.requests[0].faces) == 1
    assert compiler.requests[0].faces[0].box.left == 5.0
