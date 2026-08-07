"""The theme model: a named, serializable treatment for a caption.

A theme binds the typography personality (font stack + base ``TextStyle``),
the emphasis appearance (what each ``EmphasisMode`` does to a word), and the
animation personality (which easing identities drive each role). Themes are
pure data and load no fonts at import time; ``resolve_theme`` turns one into
a concrete ``ResolvedTheme`` against a ``FontManager``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, Field

from motion_caption.easing.functions import EasingFunction, compile_spec
from motion_caption.easing.spec import EasingSpec
from motion_caption.models.color import Color
from motion_caption.models.transcript import EmphasisMode
from motion_caption.models.units import Length
from motion_caption.typography.fonts import FontFile, FontManager, FontStack, default_font_manager
from motion_caption.typography.style import GlowSpec, TextStyle


class AnimationPersonality(BaseModel):
    """Easing identity per animation role.

    The animation-strategy phase upgrades these into full keyframe templates;
    for now the personality carries the easing curves that give a theme its
    motion character. All fields are ``EasingSpec`` so they serialize to JSON.
    """

    in_ease: EasingSpec = EasingSpec("ease-out")
    out_ease: EasingSpec = EasingSpec("ease-in")
    pop_ease: EasingSpec = EasingSpec("spring")
    idle_ease: EasingSpec = EasingSpec("linear")


class EmphasisAppearance(BaseModel):
    """The delta applied to a word when it carries an emphasis mode.

    ``None`` fields mean "leave the base style alone". ``scale`` is a
    multiplier on the base size. This is appearance data, not animation: the
    keyframe engine turns these deltas into tracks.
    """

    color: Color | None = None
    glow: GlowSpec | None = None
    scale: float = Field(default=1.0, gt=0.0)
    uppercase: bool | None = None
    weight: int | None = Field(default=None, ge=100, le=900, multiple_of=100)
    letter_spacing: Length | None = None


def _default_stack() -> FontStack:
    return FontStack(fonts=["Helvetica"])


class ThemeSpec(BaseModel):
    """A named, resolution-independent caption treatment.

    ``font_stack`` is the font authority: ``resolve_theme`` injects it into
    the base style's ``font``. The built-in catalog ships in ``catalog.py``;
    third parties register new themes via ``THEME_REGISTRY``.
    """

    name: str
    display_name: str | None = None
    description: str | None = None
    font_stack: FontStack = Field(default_factory=_default_stack)
    style: TextStyle = Field(default_factory=TextStyle)
    emphasis: dict[Annotated[EmphasisMode, "theme emphasis appearance"], EmphasisAppearance] = (
        Field(default_factory=dict)
    )
    animation: AnimationPersonality = Field(default_factory=AnimationPersonality)
    tags: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ResolvedTheme:
    """A theme bound to concrete fonts and callable easings.

    Consumers (animation strategies, renderers) use this; it never hits disk
    or the font catalog again.
    """

    spec: ThemeSpec
    fonts: tuple[FontFile, ...]
    base_style: TextStyle
    emphasis: dict[EmphasisMode, EmphasisAppearance]
    easings: dict[str, EasingFunction]
    easing_specs: dict[str, EasingSpec]


def resolve_theme(
    spec: ThemeSpec,
    font_manager: FontManager | None = None,
) -> ResolvedTheme:
    """Bind a theme to fonts and easing functions (lazy, cached upstream)."""
    manager = font_manager or default_font_manager()
    fonts = tuple(manager.resolve_stack(spec.font_stack))
    base_style = spec.style.model_copy(update={"font": spec.font_stack})
    easings = {
        "in": compile_spec(spec.animation.in_ease),
        "out": compile_spec(spec.animation.out_ease),
        "pop": compile_spec(spec.animation.pop_ease),
        "idle": compile_spec(spec.animation.idle_ease),
    }
    return ResolvedTheme(
        spec=spec,
        fonts=fonts,
        base_style=base_style,
        emphasis=dict(spec.emphasis),
        easings=easings,
        easing_specs={
            "in": spec.animation.in_ease,
            "out": spec.animation.out_ease,
            "pop": spec.animation.pop_ease,
            "idle": spec.animation.idle_ease,
        },
    )
