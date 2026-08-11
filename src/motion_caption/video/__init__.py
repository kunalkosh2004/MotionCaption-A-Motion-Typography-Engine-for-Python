"""Application video layer: FFmpeg bridge, transcript providers, pipeline.

Everything here lives *above* the compiler: it orchestrates media I/O and
external integrations but never touches ``SubtitleTimeline`` construction.
The core package remains importable without ``ffmpeg`` installed.
"""

from __future__ import annotations

from motion_caption.video.faces import (
    FaceDetector,
    OpenCVFaceDetector,
    detect_faces_for_video,
)
from motion_caption.video.ffmpeg import (
    FFmpegVideoProcessor,
    VideoMetadata,
    temporary_directory,
)
from motion_caption.video.gemini import GeminiTranscriptProvider
from motion_caption.video.pipeline import CaptionVideoPipeline, PipelineResult
from motion_caption.video.presets import (
    PLATFORM_PRESETS,
    PlatformPreset,
    available_presets,
    platform_preset,
)
from motion_caption.video.transcript import (
    FakeTranscriptProvider,
    TranscriptProvider,
    normalize_transcript,
    split_segment_words,
    validate_transcript,
)
from motion_caption.video.whisperx import WhisperXTranscriptProvider

__all__ = [
    "CaptionVideoPipeline",
    "FFmpegVideoProcessor",
    "FaceDetector",
    "FakeTranscriptProvider",
    "GeminiTranscriptProvider",
    "OpenCVFaceDetector",
    "PLATFORM_PRESETS",
    "PipelineResult",
    "PlatformPreset",
    "TranscriptProvider",
    "VideoMetadata",
    "WhisperXTranscriptProvider",
    "available_presets",
    "detect_faces_for_video",
    "normalize_transcript",
    "platform_preset",
    "split_segment_words",
    "temporary_directory",
    "validate_transcript",
]
