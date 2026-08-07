"""Layout subsystem: measured blocks → positioned, aligned regions."""

from motion_caption.layout.engine import (
    LayoutEngine,
    LayoutOptions,
    PlacedBlock,
    lay_out,
)

__all__ = [
    "LayoutEngine",
    "LayoutOptions",
    "PlacedBlock",
    "lay_out",
]
