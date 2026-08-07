"""Geometry value objects shared across all subsystems."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from motion_caption.models.units import Length, ResolutionContext


class Point(BaseModel):
    x: float = 0.0
    y: float = 0.0

    def __init__(self, x: object = None, y: object = None, **data: object) -> None:
        if x is not None:
            data["x"] = x
        if y is not None:
            data["y"] = y
        super().__init__(**data)

    def __add__(self, other: Point) -> Point:
        return Point(x=self.x + other.x, y=self.y + other.y)

    def __sub__(self, other: Point) -> Point:
        return Point(x=self.x - other.x, y=self.y - other.y)


class Size(BaseModel):
    width: float = 0.0
    height: float = 0.0

    def __init__(self, width: object = None, height: object = None, **data: object) -> None:
        if width is not None:
            data["width"] = width
        if height is not None:
            data["height"] = height
        super().__init__(**data)


class Box(BaseModel):
    """An axis-aligned box. Constructed from edges; widths are derived."""

    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    model_config = ConfigDict(frozen=True)

    def __init__(
        self,
        left: object = None,
        top: object = None,
        right: object = None,
        bottom: object = None,
        **data: object,
    ) -> None:
        if left is not None:
            data["left"] = left
        if top is not None:
            data["top"] = top
        if right is not None:
            data["right"] = right
        if bottom is not None:
            data["bottom"] = bottom
        super().__init__(**data)

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def size(self) -> Size:
        return Size(width=self.width, height=self.height)

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0

    @classmethod
    def from_point_size(cls, point: Point, size: Size) -> Box:
        return cls(
            left=point.x,
            top=point.y,
            right=point.x + size.width,
            bottom=point.y + size.height,
        )

    @classmethod
    def from_xywh(cls, x: float, y: float, w: float, h: float) -> Box:
        return cls(left=x, top=y, right=x + w, bottom=y + h)

    def contains(self, point: Point) -> bool:
        return self.left <= point.x <= self.right and self.top <= point.y <= self.bottom

    def translate(self, dx: float, dy: float) -> Box:
        return Box(
            left=self.left + dx,
            top=self.top + dy,
            right=self.right + dx,
            bottom=self.bottom + dy,
        )

    def scale(self, factor: float) -> Box:
        return Box(
            left=self.left * factor,
            top=self.top * factor,
            right=self.right * factor,
            bottom=self.bottom * factor,
        )

    def union(self, other: Box) -> Box:
        return Box(
            left=min(self.left, other.left),
            top=min(self.top, other.top),
            right=max(self.right, other.right),
            bottom=max(self.bottom, other.bottom),
        )


class Padding(BaseModel):
    """Resolution-independent padding, resolved against a context."""

    left: Length = Length(0)
    top: Length = Length(0)
    right: Length = Length(0)
    bottom: Length = Length(0)

    @classmethod
    def uniform(cls, value: Length) -> Padding:
        return cls(left=value, top=value, right=value, bottom=value)

    def resolve(self, ctx: ResolutionContext) -> Box:
        """Resolve to a float-edged box (edge amounts, not a region)."""
        return Box(
            left=self.left.resolve(ctx),
            top=self.top.resolve(ctx),
            right=self.right.resolve(ctx),
            bottom=self.bottom.resolve(ctx),
        )

    def is_zero(self) -> bool:
        return (
            self.left.value == 0
            and self.top.value == 0
            and self.right.value == 0
            and self.bottom.value == 0
        )
