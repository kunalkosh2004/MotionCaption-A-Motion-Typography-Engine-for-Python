"""Application-level error hierarchy for MotionCaption.

The compiler core raises plain ``ValueError`` / ``KeyError`` / ``TypeError``
(those types are pinned by the core test suite and are correct for model
validation). This hierarchy exists for the application and integration layers —
video pipeline, FFmpeg bridge, transcript providers, AI providers, exporters,
plugins and the CLI — where callers need to distinguish failure modes
programmatically.

Every error carries an optional ``hint``: a short, actionable "what to do next"
sentence surfaced by the CLI and logs. Errors are never used for control flow;
they always represent a real failure with a user-facing explanation.

``AIProviderError`` intentionally subclasses ``RuntimeError`` as well, so the
historical missing-API-key ``RuntimeError`` contract keeps working while
callers gain a specific catchable type.
"""

from __future__ import annotations


class MotionCaptionError(Exception):
    """Base class for all MotionCaption application errors."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        if self.hint:
            return f"{self.message} ({self.hint})"
        return self.message


class InvalidTranscriptError(MotionCaptionError):
    """The transcript is empty, malformed, or not usable for captioning."""


class TranscriptionError(MotionCaptionError):
    """A transcript provider failed to produce a transcript."""


class AIProviderError(MotionCaptionError, RuntimeError):
    """An AI provider is missing configuration or failed during annotation."""


class FFmpegError(MotionCaptionError):
    """FFmpeg/ffprobe is missing, timed out, or failed on a command."""


class InvalidVideoError(FFmpegError):
    """The input is not a valid, decodable media file."""


class RequestIOError(MotionCaptionError):
    """A request/transcript/timeline file could not be read or written."""


class ExportError(MotionCaptionError):
    """A backend failed to export a timeline."""


class PluginError(MotionCaptionError):
    """Plugin loading or registration failed."""
