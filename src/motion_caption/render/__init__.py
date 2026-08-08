"""Render subsystem: sample timelines → raster frames (Pillow)."""

from motion_caption.render.engine import CaptionRenderer, RenderOptions
from motion_caption.render.timeline import TimelineRenderer

__all__ = [
    "CaptionRenderer",
    "RenderOptions",
    "TimelineRenderer",
]
