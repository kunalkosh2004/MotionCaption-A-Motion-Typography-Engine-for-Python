"""The text style model: every typography knob in one immutable spec.

Styles are resolution-independent: every measurable quantity is a ``Length``
resolved against a ``ResolutionContext`` at measurement/render time. A style
describes one text block; themes assemble styles into caption treatments.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from motion_caption.models.color import Color, FillSpec
from motion_caption.models.geometry import Padding
from motion_caption.models.units import Length
from motion_caption.typography.fonts import FontStack


class TextAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class StrokeSpec(BaseModel):
    """An outline stroke around the glyphs."""

    width: Length = Length(0)
    color: Color = Field(default_factory=lambda: Color("#000000"))
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class ShadowOffset(BaseModel):
    dx: Length = Length(0)
    dy: Length = Length(0)


class ShadowSpec(BaseModel):
    """A drop shadow behind the glyphs."""

    offset: ShadowOffset = Field(default_factory=lambda: ShadowOffset(dx=Length(2), dy=Length(2)))
    blur: Length = Length(0)
    color: Color = Field(default_factory=lambda: Color("#000000"))
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class GlowSpec(BaseModel):
    """A soft halo behind the glyphs (ass/expanded-stroke glow)."""

    color: Color = Field(default_factory=lambda: Color("#FFFFFF"))
    spread: Length = Length(0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class BorderSpec(BaseModel):
    width: Length = Length(1)
    color: Color = Field(default_factory=lambda: Color("#000000"))


class BackgroundSpec(BaseModel):
    """A rounded background box behind the whole text block."""

    fill: FillSpec | None = None
    padding: Padding = Field(default_factory=lambda: Padding.uniform(Length(16)))
    corner_radius: Length = Length(0)
    border: BorderSpec | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    blur: Length = Length(0)


class TextStyle(BaseModel):
    """The full typography specification for a caption block.

    Defaults are sensible for a 1920x1080 design space; themes override them.
    """

    font: FontStack = Field(default_factory=lambda: FontStack(fonts=["Helvetica"]))
    size: Length = Length(56)
    letter_spacing: Length = Length(0)
    word_spacing: Length = Length(0)
    line_height: Length = Length(1.2, unit="em")
    fill: FillSpec = Field(default_factory=lambda: FillSpec(color=Color("#FFFFFF")))
    stroke: StrokeSpec | None = None
    shadow: ShadowSpec | None = None
    glow: GlowSpec | None = None
    background: BackgroundSpec | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    blur: Length = Length(0)
    uppercase: bool = False
    align: TextAlign = TextAlign.CENTER
