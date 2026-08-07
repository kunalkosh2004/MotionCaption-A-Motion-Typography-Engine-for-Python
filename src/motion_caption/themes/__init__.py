"""Theme subsystem: named caption treatments (fonts, styles, emphasis, motion)."""

from motion_caption.themes.catalog import (
    THEME_REGISTRY,
    builtin_themes,
    load_theme,
)
from motion_caption.themes.spec import (
    AnimationPersonality,
    EmphasisAppearance,
    ResolvedTheme,
    ThemeSpec,
    resolve_theme,
)

__all__ = [
    "THEME_REGISTRY",
    "AnimationPersonality",
    "EmphasisAppearance",
    "ResolvedTheme",
    "ThemeSpec",
    "builtin_themes",
    "load_theme",
    "resolve_theme",
]
