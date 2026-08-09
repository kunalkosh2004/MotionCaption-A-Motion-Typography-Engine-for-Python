"""Application video layer: FFmpeg bridge, transcript providers, pipeline.

Everything here lives *above* the compiler: it orchestrates media I/O and
external integrations but never touches ``SubtitleTimeline`` construction.
The core package remains importable without ``ffmpeg`` installed.
"""

from __future__ import annotations

from motion_caption.video.ffmpeg import (
    FFmpegVideoProcessor,
    VideoMetadata,
    temporary_directory,
)

__all__ = ["FFmpegVideoProcessor", "VideoMetadata", "temporary_directory"]
