"""Resolved typography: a ``TextStyle`` with every ``Length`` resolved to
design-space pixels and fonts resolved to concrete faces.

This is what renderers and exporters draw from. Nothing downstream ever
re-resolves a length or consults a font catalog; the resolution happened once,
in the compiler's typography stage.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from motion_caption.models.color import Color, GradientFill
from motion_caption.typography.style import TextAlign


class ResolvedFont(BaseModel):
    """A concrete font face plus the request used to find it.

    ``family``/``weight``/``italic`` feed named-style exporters (ASS fontname
    and bold flag); ``path``/``index`` feed rasterizers (Pillow).
    """

    family: str
    weight: int = Field(default=400, ge=100, le=900, multiple_of=100)
    italic: bool = False
    path: str
    index: int = Field(default=0, ge=0)


class ResolvedStroke(BaseModel):
    width: float
    color: Color
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class ResolvedShadow(BaseModel):
    offset_x: float
    offset_y: float
    blur: float
    color: Color
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class ResolvedGlow(BaseModel):
    color: Color
    spread: float
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class ResolvedBorder(BaseModel):
    width: float
    color: Color


class ResolvedPadding(BaseModel):
    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0


class ResolvedBackground(BaseModel):
    """A rounded background box behind a text block, fully resolved."""

    fill: Color | None = None
    fill_gradient: GradientFill | None = None
    padding: ResolvedPadding = Field(default_factory=ResolvedPadding)
    corner_radius: float = 0.0
    border: ResolvedBorder | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    blur: float = 0.0


class ResolvedTypography(BaseModel):
    """The full typography of a caption block or word, in design-space px.

    All lengths are floats. ``align`` is kept so text exporters can emit
    alignment tags; everything else is pure geometry/color.
    """

    font: ResolvedFont
    font_size: float = Field(gt=0.0)
    fill: Color = Field(default_factory=lambda: Color("#FFFFFF"))
    fill_gradient: GradientFill | None = None
    stroke: ResolvedStroke | None = None
    shadow: ResolvedShadow | None = None
    glow: ResolvedGlow | None = None
    background: ResolvedBackground | None = None
    letter_spacing: float = 0.0
    word_spacing: float = 0.0
    line_height: float = 1.2
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    blur: float = 0.0
    uppercase: bool = False
    align: TextAlign = TextAlign.CENTER
