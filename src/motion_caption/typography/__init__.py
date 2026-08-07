"""Typography subsystem: fonts, styles, and measurement."""

from motion_caption.typography.fonts import (
    FontCatalog,
    FontFile,
    FontManager,
    FontRef,
    FontStack,
    FontStyle,
    default_font_directories,
    default_font_manager,
)
from motion_caption.typography.measure import (
    MeasuredBlock,
    MeasuredLine,
    MeasuredWord,
    TextMeasurer,
)
from motion_caption.typography.style import (
    BackgroundSpec,
    BorderSpec,
    GlowSpec,
    ShadowOffset,
    ShadowSpec,
    StrokeSpec,
    TextAlign,
    TextStyle,
)

__all__ = [
    "BackgroundSpec",
    "BorderSpec",
    "FontCatalog",
    "FontFile",
    "FontManager",
    "FontRef",
    "FontStack",
    "FontStyle",
    "GlowSpec",
    "MeasuredBlock",
    "MeasuredLine",
    "MeasuredWord",
    "ShadowOffset",
    "ShadowSpec",
    "StrokeSpec",
    "TextAlign",
    "TextMeasurer",
    "TextStyle",
    "default_font_directories",
    "default_font_manager",
]
