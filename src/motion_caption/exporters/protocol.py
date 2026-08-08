"""Exporter contract: every backend consumes only ``SubtitleTimeline``.

No exporter measures, picks fonts, lays out or animates — the compiler did
all of that. A backend re-interprets the IR and returns bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from motion_caption.ir.timeline import SubtitleTimeline


@dataclass(frozen=True)
class ExporterResult:
    """A backend's output: data plus a media type and file extension."""

    data: str | bytes
    media_type: str = "text/plain"
    extension: str = "txt"


class Exporter(Protocol):
    """A backend that renders a compiled timeline into an ``ExporterResult``.

    Implementations may accept extra keyword options (e.g. ``fps``), since a
    call with only ``timeline`` must always succeed.
    """

    name: str

    def export(self, timeline: SubtitleTimeline) -> ExporterResult: ...
