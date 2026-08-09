"""File IO for the serializable core models.

``CaptionRequest``, ``Transcript`` and ``SubtitleTimeline`` are pure data
(pydantic), so they round-trip through JSON. This module is the thin, typed
bridge between disk and the compiler:

    JSON ──load_request──▶ CaptionRequest ──compile──▶ SubtitleTimeline
                                                          │
    JSON ◀────save_timeline───────────────────────────────┘

Load failures raise typed errors with the *reason* and a hint (the last line
of the pydantic error is usually the actionable one); write failures raise
``RequestIOError``. The JSON exporter remains the canonical way to serialize
a timeline for distribution — this module adds the read side and convenience
writers.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from motion_caption.errors import InvalidTranscriptError, RequestIOError
from motion_caption.ir.request import CaptionRequest
from motion_caption.ir.timeline import SubtitleTimeline
from motion_caption.models import Transcript


def _read_text(path: str | Path) -> str:
    source = Path(path)
    try:
        return source.read_text(encoding="utf-8")
    except OSError as exc:
        raise RequestIOError(
            f"cannot read {source}",
            hint=f"{exc.strerror or exc}; check the path is correct",
        ) from exc


def load_request(path: str | Path) -> CaptionRequest:
    """Load and validate a ``CaptionRequest`` from a JSON file."""
    try:
        return CaptionRequest.model_validate_json(_read_text(path))
    except ValidationError as exc:
        raise RequestIOError(
            f"invalid CaptionRequest JSON in {path}",
            hint=_hint(exc),
        ) from exc


def load_transcript(path: str | Path) -> Transcript:
    """Load a ``Transcript`` from JSON (accepts a bare word list too)."""
    try:
        return Transcript.model_validate_json(_read_text(path))
    except ValidationError as exc:
        raise InvalidTranscriptError(
            f"invalid transcript JSON in {path}",
            hint=_hint(exc),
        ) from exc


def load_timeline(path: str | Path) -> SubtitleTimeline:
    """Load a previously saved ``SubtitleTimeline`` from JSON."""
    try:
        return SubtitleTimeline.model_validate_json(_read_text(path))
    except ValidationError as exc:
        raise RequestIOError(
            f"invalid SubtitleTimeline JSON in {path}",
            hint=_hint(exc),
        ) from exc


def _write_text(path: str | Path, content: str) -> Path:
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise RequestIOError(
            f"cannot write {target}",
            hint=f"{exc.strerror or exc}; check the directory is writable",
        ) from exc
    return target


def save_request(request: CaptionRequest, path: str | Path) -> Path:
    """Serialize a request to a JSON file (round-trips through ``load_request``)."""
    return _write_text(path, request.model_dump_json(indent=2) + "\n")


def save_timeline(timeline: SubtitleTimeline, path: str | Path) -> Path:
    """Serialize a compiled timeline to a JSON file."""
    return _write_text(path, timeline.model_dump_json(indent=2) + "\n")


def _hint(exc: ValidationError) -> str:
    lines = str(exc).splitlines()
    detail = lines[-1].strip() if lines else str(exc)
    return detail[:200]
