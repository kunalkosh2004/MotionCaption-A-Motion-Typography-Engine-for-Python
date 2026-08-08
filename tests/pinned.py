"""Pinned-font test harness helpers.

Golden frames, timeline snapshots and animation snapshots must be
byte-stable on any machine, so they all render through the bundled
``tests/fonts/Roboto-Regular.ttf`` referenced **by path** — never the system
font catalog. These helpers are plain functions (no pytest dependency) so
both ``conftest.py`` fixtures and ``benchmarks/bench.py`` can use them.
"""

from __future__ import annotations

from pathlib import Path

from motion_caption.compiler.engine import Compiler
from motion_caption.models.transcript import EmphasisMode
from motion_caption.themes.spec import (
    AnimationPersonality,
    EmphasisAppearance,
    ResolvedTheme,
    ThemeSpec,
    resolve_theme,
)
from motion_caption.typography.fonts import FontCatalog, FontManager, FontRef, FontStack

FONTS_DIR = Path(__file__).resolve().parent / "fonts"
ROBOTO_PATH = FONTS_DIR / "Roboto-Regular.ttf"


def pinned_font_ref() -> FontRef:
    """A path-bound Roboto request (weight 400)."""
    return FontRef(family="Roboto", weight=400, path=str(ROBOTO_PATH))


def pinned_font_manager() -> FontManager:
    """A manager whose catalog is only the bundled fonts directory."""
    return FontManager(catalog=FontCatalog([FONTS_DIR]))


def pinned_theme_spec() -> ThemeSpec:
    """A deterministic theme exercising every rendering feature: fill,
    letter-spacing, shadow, glow, background box, and two emphasis modes.
    """
    return ThemeSpec(
        name="pinned_golden",
        display_name="Pinned Golden",
        description="Deterministic test theme over the bundled Roboto font.",
        font_stack=FontStack(fonts=[pinned_font_ref()]),
        style={
            "size": "56px",
            "letter_spacing": "1px",
            "fill": {"color": "#FFFFFF"},
            "shadow": {
                "offset": {"dx": "2px", "dy": "2px"},
                "blur": "2px",
                "opacity": 0.6,
            },
            "glow": {"color": "#00E5FF", "spread": "6px", "opacity": 0.5},
            "background": {
                "fill": {"color": "#111111"},
                "corner_radius": "10px",
                "opacity": 0.85,
            },
        },
        emphasis={
            EmphasisMode.HIGH: EmphasisAppearance(
                color="#00E5FF",
                scale=1.18,
                glow={"color": "#00E5FF", "spread": "12px", "opacity": 0.8},
            ),
            EmphasisMode.KARAOKE: EmphasisAppearance(color="#4FC3F7"),
        },
        animation=AnimationPersonality(
            in_ease="spring",
            pop_ease="elastic",
            out_ease="ease-in",
        ),
        tags=["test", "golden"],
    )


def pinned_theme(font_manager: FontManager | None = None) -> ResolvedTheme:
    """Resolve the pinned theme against the pinned manager."""
    return resolve_theme(pinned_theme_spec(), font_manager or pinned_font_manager())


def pinned_compiler(font_manager: FontManager | None = None) -> Compiler:
    """A Compiler whose font resolution is fully pinned."""
    return Compiler(font_manager=font_manager or pinned_font_manager())
