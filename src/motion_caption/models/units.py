"""Length, resolution and scale primitives.

Lengths are resolution-independent: ``px`` values are authored against a
reference design space and scaled to the output canvas at resolve time,
while ``em``/``%``/``vw``/``vh`` are self- or canvas-relative.
"""

from __future__ import annotations

import math
import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Unit(StrEnum):
    """The unit system for all measurable lengths in MotionCaption."""

    PX = "px"  # design-space pixels, scaled by the design-space factor
    EM = "em"  # relative to the current font size
    PERCENT = "%"  # fraction of the reference frame's minor dimension
    VW = "vw"  # fraction of the output canvas width
    VH = "vh"  # fraction of the output canvas height


_LENGTH_PATTERN = re.compile(r"^\s*([-+]?[0-9]*\.?[0-9]+)\s*(px|em|%|vw|vh)?\s*$")


class Length(BaseModel):
    """A typed, resolution-independent length.

    Can be built from a number (``Length(12)``), a CSS-like string
    (``"1.5em"``, ``"10%"``), a ``{value, unit}`` dict, or another ``Length``.
    """

    value: float
    unit: Unit = Unit.PX

    model_config = ConfigDict(frozen=True)

    def __init__(
        self,
        value: object = None,
        *,
        unit: Unit | str | None = None,
        **data: object,
    ) -> None:
        """Ergonomically accept ``Length(12)`` and ``Length(1.5, unit="em")``."""
        if isinstance(value, (int, float)):
            data["value"] = float(value)
            if unit is not None:
                data["unit"] = unit
        elif isinstance(value, str):
            data["value"] = value
        elif isinstance(value, dict):
            data.update(value)
        elif isinstance(value, Length):
            data.setdefault("value", value.value)
            data.setdefault("unit", value.unit)
        elif value is not None:
            data["value"] = value
        data.setdefault("value", 0.0)
        super().__init__(**data)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if isinstance(data, Length):
            return data
        if isinstance(data, (int, float)):
            return {"value": float(data), "unit": Unit.PX}
        if isinstance(data, str):
            match = _LENGTH_PATTERN.match(data)
            if match is None:
                raise ValueError(f"invalid length: {data!r}")
            number, unit = match.group(1), match.group(2)
            return {
                "value": float(number),
                "unit": Unit(unit) if unit else Unit.PX,
            }
        if isinstance(data, dict):
            if isinstance(data.get("value"), str):
                inner = cls._coerce(data["value"])
                assert isinstance(inner, dict)
                merged = dict(data)
                merged["value"] = inner["value"]
                merged.setdefault("unit", inner["unit"])
                return merged
            return data
        raise ValueError(f"cannot build Length from {data!r}")

    def resolve(
        self,
        ctx: ResolutionContext,
        *,
        percent_base: float | None = None,
    ) -> float:
        """Resolve this length to output pixels for a given context."""
        return _resolve_length(self.value, self.unit, ctx, percent_base)


def _resolve_length(
    value: float,
    unit: Unit,
    ctx: ResolutionContext,
    percent_base: float | None,
) -> float:
    if unit is Unit.PX:
        return value * ctx.scale
    if unit is Unit.EM:
        if ctx.font_size is None:
            raise ValueError("EM length requires a font_size on the resolution context")
        return value * ctx.font_size
    if unit is Unit.PERCENT:
        base = (
            percent_base
            if percent_base is not None
            else min(ctx.design.reference.width, ctx.design.reference.height)
        )
        return value / 100.0 * base * ctx.scale
    if unit is Unit.VW:
        return value / 100.0 * ctx.canvas.width
    if unit is Unit.VH:
        return value / 100.0 * ctx.canvas.height
    raise ValueError(f"unsupported unit: {unit!r}")


class Resolution(BaseModel):
    """A pixel resolution."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)

    def __init__(self, width: object = None, height: object = None, **data: object) -> None:
        if width is not None:
            data["width"] = width
        if height is not None:
            data["height"] = height
        super().__init__(**data)

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def diagonal(self) -> float:
        return math.hypot(self.width, self.height)

    def is_portrait(self) -> bool:
        return self.height >= self.width

    def is_landscape(self) -> bool:
        return self.width > self.height

    def is_square(self) -> bool:
        return self.width == self.height


class ScalePolicy(StrEnum):
    """How the design space maps onto the output canvas."""

    COVER = "cover"  # scale to fill the canvas (scale = max ratio)
    FIT = "fit"  # scale to fit inside the canvas (scale = min ratio)
    STRETCH = "stretch"  # uniform scale; anisotropy is a layout concern
    NONE = "none"  # no scaling, design units are output pixels

    def scale(self, canvas: Resolution, reference: Resolution) -> float:
        rx = canvas.width / reference.width
        ry = canvas.height / reference.height
        if self is ScalePolicy.COVER:
            return max(rx, ry)
        if self is ScalePolicy.FIT:
            return min(rx, ry)
        if self is ScalePolicy.STRETCH:
            return min(rx, ry)
        return 1.0


class DesignSpace(BaseModel):
    """The reference resolution a style was authored against."""

    reference: Resolution = Field(default_factory=lambda: Resolution(width=1920, height=1080))
    policy: ScalePolicy = ScalePolicy.COVER

    def scale_for(self, canvas: Resolution) -> float:
        return self.policy.scale(canvas, self.reference)


class ResolutionContext(BaseModel):
    """Everything needed to resolve a ``Length`` at render time."""

    canvas: Resolution
    design: DesignSpace = Field(default_factory=DesignSpace)
    font_size: float | None = None

    @property
    def scale(self) -> float:
        return self.design.scale_for(self.canvas)
