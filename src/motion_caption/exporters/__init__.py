"""Exporter subsystem: reinterpret the canonical timeline for other formats.

Backends implement the ``Exporter`` protocol and consume only
``SubtitleTimeline``. The registry dispatches by name (no switch statements);
entry-point group ``motion_caption.exporters`` will load third-party backends.
"""

from motion_caption.exporters.ass import AssExporter, AssOptions, build_ass
from motion_caption.exporters.json import JsonExporter
from motion_caption.exporters.protocol import Exporter, ExporterResult
from motion_caption.registry import Registry

EXPORTER_REGISTRY: Registry[Exporter] = Registry("exporter")
EXPORTER_REGISTRY.add("ass", AssExporter(), overwrite=True)
EXPORTER_REGISTRY.add("json", JsonExporter(), overwrite=True)

__all__ = [
    "AssExporter",
    "AssOptions",
    "EXPORTER_REGISTRY",
    "Exporter",
    "ExporterResult",
    "JsonExporter",
    "build_ass",
]
