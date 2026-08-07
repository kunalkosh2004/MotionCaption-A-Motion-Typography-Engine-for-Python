"""Built-in theme catalog.

Themes are pure data (``ThemeSpec``); nothing loads fonts at import time —
``resolve_theme`` binds them against a ``FontManager`` on first use. The
catalog registers through the same ``Registry`` that third-party themes use,
so plugins can add or replace named treatments.
"""

from __future__ import annotations

from motion_caption.models.transcript import EmphasisMode
from motion_caption.registry import Registry
from motion_caption.themes.spec import AnimationPersonality, EmphasisAppearance, ThemeSpec


def _stack(*families: tuple[str, int]) -> list[dict[str, object]]:
    return [{"family": family, "weight": weight} for family, weight in families]


_CLEAN = ThemeSpec(
    name="clean",
    display_name="Clean",
    description="Neutral, modern subtitles with a soft shadow.",
    font_stack=_stack(("Helvetica", 400), ("Arial", 400)),
    style={
        "size": "56px",
        "fill": {"color": "#FFFFFF"},
        "shadow": {"offset": {"dx": "2px", "dy": "2px"}, "blur": "2px", "opacity": 0.6},
    },
    emphasis={
        EmphasisMode.HIGH: EmphasisAppearance(scale=1.1),
        EmphasisMode.KARAOKE: EmphasisAppearance(color="#4FC3F7"),
    },
    tags=["default", "minimal"],
)

_MUSIC_VIDEO = ThemeSpec(
    name="music_video",
    display_name="Music Video",
    description="Bold lyric captions with glow and a springy pop.",
    font_stack=_stack(
        ("Avenir Next", 600),
        ("Avenir", 600),
        ("Helvetica Neue", 600),
        ("Helvetica", 600),
    ),
    style={
        "size": "60px",
        "letter_spacing": "1px",
        "fill": {"color": "#FFFFFF"},
        "glow": {"color": "#00E5FF", "spread": "6px", "opacity": 0.7},
    },
    emphasis={
        EmphasisMode.MEDIUM: EmphasisAppearance(scale=1.06),
        EmphasisMode.HIGH: EmphasisAppearance(
            color="#00E5FF",
            glow={"color": "#00E5FF", "spread": "12px", "opacity": 0.8},
            scale=1.18,
        ),
        EmphasisMode.KARAOKE: EmphasisAppearance(color="#00E5FF"),
    },
    animation=AnimationPersonality(
        in_ease="spring",
        pop_ease="elastic",
        out_ease="ease-in",
    ),
    tags=["lyrics", "vibrant"],
)

_CINEMATIC = ThemeSpec(
    name="cinematic",
    display_name="Cinematic",
    description="Elegant serif letter-spaced captions with a gold accent.",
    font_stack=_stack(
        ("Georgia", 400),
        ("Times New Roman", 400),
        ("Times", 400),
    ),
    style={
        "size": "58px",
        "letter_spacing": "2px",
        "fill": {"color": "#F7F3EA"},
        "glow": {"color": "#D4AF37", "spread": "8px", "opacity": 0.5},
    },
    emphasis={
        EmphasisMode.MEDIUM: EmphasisAppearance(letter_spacing="3px"),
        EmphasisMode.HIGH: EmphasisAppearance(color="#D4AF37", letter_spacing="4px"),
    },
    animation=AnimationPersonality(
        in_ease="ease-out",
        pop_ease="overshoot",
        out_ease="ease-out",
    ),
    tags=["film", "serif", "elegant"],
)

_SPORT = ThemeSpec(
    name="sport",
    display_name="Sport",
    description="Heavy uppercase captions with a hard outline.",
    font_stack=_stack(("Impact", 400), ("Arial Black", 400), ("Helvetica", 800)),
    style={
        "size": "64px",
        "letter_spacing": "1px",
        "uppercase": True,
        "fill": {"color": "#FFD400"},
        "stroke": {"width": "4px", "color": "#000000"},
    },
    emphasis={
        EmphasisMode.HIGH: EmphasisAppearance(scale=1.25, uppercase=True),
        EmphasisMode.KARAOKE: EmphasisAppearance(color="#FFFFFF"),
    },
    animation=AnimationPersonality(
        in_ease="overshoot",
        pop_ease="bounce",
        out_ease="ease-in",
    ),
    tags=["bold", "energy"],
)

_NEWS = ThemeSpec(
    name="news",
    display_name="News",
    description="Editorial captions on a rounded background box.",
    font_stack=_stack(("Helvetica", 500), ("Arial", 500)),
    style={
        "size": "48px",
        "fill": {"color": "#FFFFFF"},
        "background": {
            "fill": {"color": "#111111"},
            "corner_radius": "8px",
            "opacity": 0.9,
        },
    },
    emphasis={
        EmphasisMode.MEDIUM: EmphasisAppearance(scale=1.05),
        EmphasisMode.HIGH: EmphasisAppearance(color="#E53935"),
    },
    tags=["editorial", "accessible"],
)

THEME_REGISTRY: Registry[ThemeSpec] = Registry("theme")

for _theme in (_CLEAN, _MUSIC_VIDEO, _CINEMATIC, _SPORT, _NEWS):
    THEME_REGISTRY.add(_theme.name, _theme, overwrite=True)

THEME_REGISTRY.add("default", _CLEAN, aliases=["clean"], overwrite=True)

_BUILTIN_ORDER = (_CLEAN, _MUSIC_VIDEO, _CINEMATIC, _SPORT, _NEWS)


def load_theme(name: str) -> ThemeSpec:
    """Look up a named theme (built-in or plugin-registered)."""
    return THEME_REGISTRY.get(name)


def builtin_themes() -> dict[str, ThemeSpec]:
    """The built-in catalog as a name → spec mapping."""
    return {theme.name: theme for theme in _BUILTIN_ORDER}
