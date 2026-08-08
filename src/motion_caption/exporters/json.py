"""JSON timeline exporter: the IR serialized as-is (free from the IR)."""

from __future__ import annotations

from motion_caption.exporters.protocol import ExporterResult
from motion_caption.ir.timeline import SubtitleTimeline


class JsonExporter:
    """Serialize a ``SubtitleTimeline`` to JSON (deterministic)."""

    name = "json"

    def export(self, timeline: SubtitleTimeline, *, indent: int = 2) -> ExporterResult:
        return ExporterResult(
            data=timeline.model_dump_json(indent=indent),
            media_type="application/json",
            extension="json",
        )
