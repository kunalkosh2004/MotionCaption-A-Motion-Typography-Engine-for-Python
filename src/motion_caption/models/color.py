"""Color and gradient value objects."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

_HEX_PATTERN = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB_PATTERN = re.compile(r"^rgba?\((.*)\)$")


class Color(BaseModel):
    """An RGBA color with human-friendly coercion."""

    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)
    a: int = Field(default=255, ge=0, le=255)

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if isinstance(data, Color):
            return data
        if isinstance(data, str):
            value = data.strip()
            match = _HEX_PATTERN.match(value)
            if match is not None:
                digits = match.group(1)
                if len(digits) in (3, 4):
                    digits = "".join(ch * 2 for ch in digits)
                red = int(digits[0:2], 16)
                green = int(digits[2:4], 16)
                blue = int(digits[4:6], 16)
                alpha = int(digits[6:8], 16) if len(digits) == 8 else 255
                return {"r": red, "g": green, "b": blue, "a": alpha}
            match = _RGB_PATTERN.match(value)
            if match is not None:
                parts = [p.strip() for p in match.group(1).split(",")]
                if len(parts) in (3, 4):
                    channels = [_color_channel(p) for p in parts]
                    return {
                        "r": channels[0],
                        "g": channels[1],
                        "b": channels[2],
                        "a": channels[3] if len(channels) == 4 else 255,
                    }
            raise ValueError(f"invalid color: {data!r}")
        if isinstance(data, (tuple, list)):
            if len(data) not in (3, 4):
                raise ValueError(f"color tuples must have 3 or 4 channels, got {len(data)}")
            channels = [_color_channel(c) for c in data]
            return {
                "r": channels[0],
                "g": channels[1],
                "b": channels[2],
                "a": channels[3] if len(channels) == 4 else 255,
            }
        if isinstance(data, dict):
            return data
        raise ValueError(f"cannot build Color from {data!r}")

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        return (self.r, self.g, self.b, self.a)

    @property
    def hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    @property
    def hex_with_alpha(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}{self.a:02X}"

    def with_alpha(self, alpha: int) -> "Color":
        return Color(r=self.r, g=self.g, b=self.b, a=alpha)

    def interpolate(self, other: "Color", t: float) -> "Color":
        t = min(1.0, max(0.0, t))
        return Color(
            r=round(self.r + (other.r - self.r) * t),
            g=round(self.g + (other.g - self.g) * t),
            b=round(self.b + (other.b - self.b) * t),
            a=round(self.a + (other.a - self.a) * t),
        )

    @property
    def luminance(self) -> float:
        """Perceptual luminance in 0..1 (Rec. 709 luma weights)."""
        return (0.2126 * self.r + 0.7152 * self.g + 0.0722 * self.b) / 255.0

    def as_ass(self) -> str:
        """ASS color: ``&H<alpha><BBGGRR>`` with alpha 00 = opaque."""
        return f"&H{self.a:02X}{self.b:02X}{self.g:02X}{self.r:02X}"

    @property
    def ass_alpha(self) -> str:
        """ASS alpha byte (00 = opaque, FF = transparent)."""
        return f"{255 - self.a:02X}"


def _color_channel(value: object) -> int:
    number = float(value)
    if number <= 1.0 and number > 0.0:
        return round(number * 255)
    return round(number)


class GradientKind(str, Enum):
    LINEAR = "linear"
    RADIAL = "radial"


class GradientStop(BaseModel):
    color: Color
    position: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(frozen=True)


class GradientFill(BaseModel):
    """A gradient sampled at arbitrary positions in 0..1."""

    kind: GradientKind = GradientKind.LINEAR
    stops: list[GradientStop] = Field(min_length=1)
    angle: float = 0.0  # degrees, clockwise from x-axis (linear only)

    model_config = ConfigDict(frozen=True)

    @property
    def is_solid(self) -> bool:
        return len(self.stops) == 1

    def sample(self, t: float) -> Color:
        t = min(1.0, max(0.0, t))
        stops = sorted(self.stops, key=lambda stop: stop.position)
        if t <= stops[0].position:
            return stops[0].color
        if t >= stops[-1].position:
            return stops[-1].color
        for (before, after) in zip(stops, stops[1:]):
            if before.position <= t <= after.position:
                span = after.position - before.position
                ratio = (t - before.position) / span if span > 0 else 0.0
                return before.color.interpolate(after.color, ratio)
        return stops[-1].color


class FillKind(str, Enum):
    SOLID = "solid"
    GRADIENT = "gradient"


class FillSpec(BaseModel):
    """The fill of a glyph or background: solid color or gradient."""

    kind: FillKind = FillKind.SOLID
    color: Color = Field(default_factory=lambda: Color(r=255, g=255, b=255))
    gradient: GradientFill | None = None

    @property
    def uses_gradient(self) -> bool:
        return self.kind is FillKind.GRADIENT and self.gradient is not None
