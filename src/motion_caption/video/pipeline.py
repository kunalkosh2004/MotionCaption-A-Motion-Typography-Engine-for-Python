"""End-to-end caption video pipeline (application layer).

``CaptionVideoPipeline`` is an *orchestrator*, not a monolith: it wires the
existing pieces — FFmpeg bridge, transcript providers, the optional AI seam,
the compiler, the streaming renderer — into one ``process()`` call:

    video.mp4 → probe → (extract audio → transcribe) → Transcript
              → [AI annotate] → CaptionRequest → compile → SubtitleTimeline
              → streamed PNG frames → FFmpeg encode → mux original audio
              → final video

Every heavy step is delegated: transcription to a ``TranscriptProvider``,
annotation to the AI seam, media I/O to ``FFmpegVideoProcessor``. The compiler
stays deterministic and never touches an LLM, FFmpeg or WhisperX. Intermediate
artifacts live in a temporary workspace that is always cleaned up; only the
final video survives.

AI is strictly optional — with no ``ai_provider`` the pipeline is fully
rule-based and needs no API key.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from motion_caption.ai import AI_REGISTRY, AIProvider, annotate
from motion_caption.canvas import Canvas
from motion_caption.compiler.engine import Compiler, default_compiler
from motion_caption.errors import (
    AIProviderError,
    InvalidTranscriptError,
    MotionCaptionError,
)
from motion_caption.ir.request import CaptionRequest
from motion_caption.ir.timeline import SubtitleTimeline
from motion_caption.models import Transcript
from motion_caption.placement import Face
from motion_caption.render import TimelineRenderer
from motion_caption.video.faces import FaceDetector, detect_faces_for_video
from motion_caption.video.ffmpeg import FFmpegVideoProcessor, VideoMetadata, temporary_directory
from motion_caption.video.transcript import (
    TranscriptProvider,
    normalize_transcript,
    validate_transcript,
)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """What ``CaptionVideoPipeline.process`` produced and how it was made."""

    output_video: Path
    timeline: SubtitleTimeline
    transcript: Transcript
    metadata: VideoMetadata
    event_count: int
    word_count: int
    frames_rendered: int
    llm_annotated: bool
    theme: str | None
    details: dict[str, Any] = field(default_factory=dict)


class CaptionVideoPipeline:
    """Compile a video + transcript into a captioned MP4.

    Args:
        theme: built-in theme name or ``ThemeSpec``.
        platform: platform tag stored on the request (e.g. ``"youtube_shorts"``);
            presets in ``motion_caption.video.presets`` fill resolution/safe areas.
        resolution: ``(width, height)`` tuple, ``"WxH"`` string or
            ``StandardResolution`` name; defaults to the input video size.
        ai_provider: ``AIProvider`` instance or a registry name (``"gemini"`` /
            ``"openai"``); ``None`` disables AI (rule-based pipeline).
        transcript_provider: default provider used when ``process`` has no
            explicit transcript.
        ffmpeg: injected ``FFmpegVideoProcessor`` (tests inject a fake).
        fps: caption frame rate (also the encode frame rate).
        clear_color: RGBA background for caption frames (transparent by default).
    """

    def __init__(
        self,
        *,
        theme: str | None = None,
        platform: str | None = None,
        resolution: tuple[int, int] | str | None = None,
        ai_provider: AIProvider | str | None = None,
        transcript_provider: TranscriptProvider | None = None,
        face_detector: FaceDetector | None = None,
        ffmpeg: FFmpegVideoProcessor | None = None,
        compiler: Compiler | None = None,
        renderer: TimelineRenderer | None = None,
        fps: int = 30,
        clear_color: tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> None:
        self.theme = theme
        self.platform = platform
        self.resolution = resolution
        self.ai_provider = ai_provider
        self.transcript_provider = transcript_provider
        self.face_detector = face_detector
        self.ffmpeg = ffmpeg or FFmpegVideoProcessor()
        self.compiler = compiler or default_compiler()
        self.renderer = renderer or TimelineRenderer()
        self.fps = fps
        self.clear_color = clear_color

    # -- helpers -------------------------------------------------------------

    def _resolve_ai_provider(self) -> AIProvider | None:
        provider = self.ai_provider
        if provider is None:
            return None
        if isinstance(provider, str):
            if provider not in AI_REGISTRY:
                raise AIProviderError(
                    f"unknown AI provider {provider!r}",
                    hint=f"available providers: {', '.join(sorted(AI_REGISTRY.keys))}",
                )
            return AI_REGISTRY[provider]
        return provider

    def _annotate(self, request: CaptionRequest) -> tuple[CaptionRequest, bool]:
        provider = self._resolve_ai_provider()
        if provider is None:
            return request, False
        try:
            return annotate(request, provider), True
        except MotionCaptionError:
            raise
        except Exception as exc:
            raise AIProviderError(
                f"AI annotation failed: {exc}",
                hint="check the provider config/API key; run without --ai to skip",
            ) from exc

    @staticmethod
    def _resolve_transcript(
        *,
        transcript: Transcript | None,
        provider: TranscriptProvider | None,
        audio_path: Path,
    ) -> Transcript:
        if transcript is not None:
            result = normalize_transcript(transcript)
        elif provider is not None:
            result = normalize_transcript(provider.transcribe(audio_path))
        else:
            raise InvalidTranscriptError(
                "no transcript source",
                hint="pass transcript= (or --transcript) or a transcript provider",
            )
        validate_transcript(result)
        return result

    # -- main entry ----------------------------------------------------------

    def process(
        self,
        input_video: str | Path,
        output_video: str | Path | None = None,
        *,
        transcript: Transcript | None = None,
        transcript_provider: TranscriptProvider | None = None,
        faces: Sequence[Face] | None = None,
    ) -> PipelineResult:
        """Caption ``input_video`` and write the result to ``output_video``.

        Uses ``transcript`` when given; otherwise falls back to
        ``transcript_provider`` (or the pipeline's default provider) which
        transcribes an extracted audio track. Intermediate frames/audio live
        in a temporary workspace and are removed before returning.
        """
        input_path = Path(input_video)
        output_path = Path(output_video) if output_video else self._default_output(input_path)

        # 1. Validate + inspect the input.
        metadata = self.ffmpeg.probe(input_path)

        provider = transcript_provider or self.transcript_provider
        with temporary_directory() as workspace:
            frames_dir = workspace / "frames"
            audio_path = workspace / "audio.wav"

            # 2. Transcript: given, or transcribed from extracted audio.
            if transcript is None and provider is not None:
                self.ffmpeg.extract_audio(input_path, audio_path)
            resolved = self._resolve_transcript(
                transcript=transcript, provider=provider, audio_path=audio_path
            )

            # 2b. Face detection (optional, sampled): union avoidance zones.
            detected_faces = list(faces or [])
            if self.face_detector is not None and not detected_faces:
                detected_faces = detect_faces_for_video(
                    self.ffmpeg,
                    self.face_detector,
                    input_path,
                    duration=metadata.duration,
                )

            # 3. Optional AI annotation through the existing seam.
            request = self._build_request(resolved, detected_faces, metadata.resolution)
            annotated, llm_annotated = self._annotate(request)

            # 4. Compile once; the timeline is the single source of truth.
            timeline = self.compiler.compile(annotated)

            # 5. Stream frames to disk (never the whole sequence in memory).
            canvas = Canvas(width=timeline.resolution.width, height=timeline.resolution.height)
            render_end = max(timeline.end, metadata.duration)
            self.renderer.render_sequence_to_directory(
                timeline,
                canvas,
                frames_dir,
                fps=self.fps,
                clear_color=self.clear_color,
                start=0.0,
                end=render_end,
            )
            frames_rendered = _count_frames(frames_dir)

            # 6. Encode frames → silent captioned video.
            captioned = workspace / "captioned.mp4"
            self.ffmpeg.render_frames_to_video(
                frames_dir,
                self.fps,
                captioned,
                width=canvas.width,
                height=canvas.height,
            )

            # 7. Mux the original audio (full quality) onto the captioned video.
            if metadata.has_audio:
                self.ffmpeg.mux_audio(captioned, input_path, output_path)
            else:
                _copy_file(captioned, output_path)

        return PipelineResult(
            output_video=output_path,
            timeline=timeline,
            transcript=resolved,
            metadata=metadata,
            event_count=len(timeline.events),
            word_count=len(timeline.words),
            frames_rendered=frames_rendered,
            llm_annotated=llm_annotated,
            theme=self.theme,
            details={
                "fps": self.fps,
                "duration": metadata.duration,
                "has_audio": metadata.has_audio,
            },
        )

    def _build_request(
        self,
        transcript: Transcript,
        faces: Sequence[Face] | None,
        source_resolution: tuple[int, int],
    ) -> CaptionRequest:
        # Explicit resolution wins; otherwise match the input video exactly.
        requested = _resolution_value(self.resolution)
        if requested is None:
            requested = f"{source_resolution[0]}x{source_resolution[1]}"
        return CaptionRequest(
            transcript=transcript,
            theme=self.theme,
            platform=self.platform,
            faces=list(faces or []),
            resolution=requested,
        )

    @staticmethod
    def _default_output(input_path: Path) -> Path:
        return input_path.parent / f"{input_path.stem}_captioned.mp4"


def _resolution_value(resolution: tuple[int, int] | str | None) -> str | tuple[int, int] | None:
    """Pass through, but normalise tuples to a \"WxH\" string (JSON-friendly)."""
    if isinstance(resolution, tuple):
        return f"{resolution[0]}x{resolution[1]}"
    return resolution


def _count_frames(frames_dir: Path) -> int:
    return sum(1 for _ in frames_dir.glob("*.png"))


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
