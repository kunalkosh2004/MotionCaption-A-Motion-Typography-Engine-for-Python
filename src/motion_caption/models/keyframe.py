"""The canonical animation model.

Every subtitle becomes keyframed property tracks (the single source of truth
for renderers and exporters). Tracks sample deterministically: before the
first keyframe the first value holds, after the last the last value holds,
and between keyframes values interpolate through the source keyframe's
easing curve.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from motion_caption.easing.functions import compile_spec
from motion_caption.easing.spec import EasingSpec
from motion_caption.models.color import Color
from motion_caption.models.geometry import Point


class PropertyKind(StrEnum):
    """Every animatable property of a caption region.

    Enumerated at component level so each track interpolates over one value
    type: scalar, 2D point, or color.
    """

    # transform
    POSITION = "position"
    SCALE = "scale"
    ROTATION = "rotation"
    OPACITY = "opacity"
    BLUR = "blur"
    LETTER_SPACING = "letter_spacing"
    # fill / stroke
    COLOR = "color"
    STROKE_WIDTH = "stroke_width"
    STROKE_COLOR = "stroke_color"
    # shadow
    SHADOW_OFFSET = "shadow_offset"
    SHADOW_BLUR = "shadow_blur"
    SHADOW_OPACITY = "shadow_opacity"
    SHADOW_COLOR = "shadow_color"
    # glow
    GLOW_SPREAD = "glow_spread"
    GLOW_OPACITY = "glow_opacity"
    GLOW_COLOR = "glow_color"


_SCALAR_KINDS = frozenset(
    {
        PropertyKind.ROTATION,
        PropertyKind.OPACITY,
        PropertyKind.BLUR,
        PropertyKind.LETTER_SPACING,
        PropertyKind.STROKE_WIDTH,
        PropertyKind.SHADOW_BLUR,
        PropertyKind.SHADOW_OPACITY,
        PropertyKind.GLOW_SPREAD,
        PropertyKind.GLOW_OPACITY,
    }
)
_POINT_KINDS = frozenset(
    {PropertyKind.POSITION, PropertyKind.SCALE, PropertyKind.SHADOW_OFFSET}
)
_COLOR_KINDS = frozenset(
    {
        PropertyKind.COLOR,
        PropertyKind.STROKE_COLOR,
        PropertyKind.SHADOW_COLOR,
        PropertyKind.GLOW_COLOR,
    }
)


_SCALAR_ADAPTER = TypeAdapter(float)
_POINT_ADAPTER = TypeAdapter(Point)
_COLOR_ADAPTER = TypeAdapter(Color)


def value_kind(kind: PropertyKind) -> str:
    """'scalar' | 'point' | 'color' for a property kind."""
    if kind in _SCALAR_KINDS:
        return "scalar"
    if kind in _POINT_KINDS:
        return "point"
    if kind in _COLOR_KINDS:
        return "color"
    raise ValueError(f"unknown property kind: {kind!r}")


def _coerce_value(kind: PropertyKind, value: object) -> float | Point | Color:
    if kind in _SCALAR_KINDS:
        if isinstance(value, (Point, Color)):
            raise ValueError(f"property {kind.value} expects a scalar, got {type(value).__name__}")
        return _SCALAR_ADAPTER.validate_python(value)
    if kind in _POINT_KINDS:
        if isinstance(value, (int, float)):
            return Point(x=float(value), y=float(value))
        return _POINT_ADAPTER.validate_python(value)
    return _COLOR_ADAPTER.validate_python(value)


def interpolate_value(
    a: float | Point | Color, b: float | Point | Color, t: float
) -> float | Point | Color:
    """Linear interpolation between two like-typed values (t clamped 0..1)."""
    if isinstance(a, float) and isinstance(b, float):
        return a + (b - a) * t
    if isinstance(a, Point) and isinstance(b, Point):
        return Point(
            x=a.x + (b.x - a.x) * t,
            y=a.y + (b.y - a.y) * t,
        )
    if isinstance(a, Color) and isinstance(b, Color):
        return a.interpolate(b, t)
    raise TypeError(f"cannot interpolate {type(a).__name__} and {type(b).__name__}")


class Keyframe(BaseModel):
    """A single keyframe: time, value, and the easing out of it."""

    time: float = Field(ge=0.0)
    value: float | Point | Color
    ease: EasingSpec = EasingSpec("linear")

    model_config = ConfigDict(frozen=True)

    def __init__(
        self,
        time: object = None,
        value: object = None,
        ease: object = None,
        **data: object,
    ) -> None:
        """Ergonomic construction: ``Keyframe(0.5, value, ease="ease-in-out")``."""
        if time is not None:
            data.setdefault("time", time)
        if value is not None:
            data.setdefault("value", value)
        if ease is not None:
            data.setdefault("ease", ease)
        super().__init__(**data)


class KeyframeTimeline(BaseModel):
    """An ordered set of keyframes for one property, with deterministic sampling."""

    kind: PropertyKind
    keyframes: list[Keyframe] = Field(min_length=1)

    @model_validator(mode="after")
    def _normalize(self) -> KeyframeTimeline:
        ordered = sorted(self.keyframes, key=lambda k: k.time)
        normalized = [
            k.model_copy(update={"value": _coerce_value(self.kind, k.value)})
            for k in ordered
        ]
        self.keyframes = normalized
        return self

    @property
    def start(self) -> float:
        return self.keyframes[0].time

    @property
    def end(self) -> float:
        return self.keyframes[-1].time

    @property
    def value_type(self) -> str:
        return value_kind(self.kind)

    def sample(self, t: float) -> float | Point | Color:
        """Sample the track at time t (holds outside the keyframe range)."""
        keyframes = self.keyframes
        if t <= keyframes[0].time:
            return keyframes[0].value
        if t >= keyframes[-1].time:
            return keyframes[-1].value
        for index in range(len(keyframes) - 1):
            source, target = keyframes[index], keyframes[index + 1]
            if source.time <= t <= target.time:
                span = target.time - source.time
                progress = (t - source.time) / span if span > 0 else 1.0
                eased = compile_spec(source.ease)(progress)
                return interpolate_value(source.value, target.value, eased)
        return keyframes[-1].value


class Region(BaseModel):
    """A fully-sampled snapshot of a caption region at one instant.

    Field names match ``PropertyKind`` values so a sampled {kind: value} map
    can be applied directly.
    """

    position: Point = Point(0, 0)
    scale: Point = Point(1, 1)
    rotation: float = 0.0
    opacity: float = 1.0
    blur: float = 0.0
    letter_spacing: float = 0.0
    color: Color | None = None
    stroke_width: float = 0.0
    stroke_color: Color | None = None
    shadow_offset: Point = Point(0, 0)
    shadow_blur: float = 0.0
    shadow_opacity: float = 0.0
    shadow_color: Color | None = None
    glow_spread: float = 0.0
    glow_opacity: float = 0.0
    glow_color: Color | None = None


class RegionTimeline(BaseModel):
    """A composition of per-property tracks; samples to a ``Region``."""

    tracks: dict[PropertyKind, KeyframeTimeline] = Field(default_factory=dict)

    def add_track(self, track: KeyframeTimeline) -> RegionTimeline:
        self.tracks[track.kind] = track
        return self

    def sample(self, t: float) -> Region:
        data: dict[str, Any] = {}
        for kind, track in self.tracks.items():
            data[kind.value] = track.sample(t)
        return Region(**data)
