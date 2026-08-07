"""Layout: measured text blocks → positioned, aligned regions on a canvas.

``lay_out`` is the pure positioning step: it takes an already-measured
``MeasuredBlock`` and returns a ``PlacedBlock`` whose word boxes carry
absolute canvas coordinates. ``LayoutEngine`` is the facade that measures,
wraps (to a max width) and positions in one call.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from motion_caption.canvas import Canvas
from motion_caption.models.geometry import Box, Padding
from motion_caption.models.units import Length, ResolutionContext
from motion_caption.typography.measure import MeasuredBlock, TextMeasurer
from motion_caption.typography.style import TextAlign, TextStyle


class LayoutOptions(BaseModel):
    """Resolution-independent layout knobs for positioning a text block."""

    align: TextAlign = TextAlign.CENTER
    max_width: Length = Length(85, unit="vw")
    margin: Padding = Field(default_factory=Padding)
    vertical_bias: float = Field(default=1.0, ge=0.0, le=1.0)

    model_config = {"arbitrary_types_allowed": True}


class PlacedBlock(BaseModel):
    """A measured block at absolute canvas coordinates."""

    block: MeasuredBlock
    box: Box

    model_config = {"arbitrary_types_allowed": True}

    @property
    def width(self) -> float:
        return self.box.width

    @property
    def height(self) -> float:
        return self.box.height

    def translate(self, dx: float, dy: float) -> PlacedBlock:
        return PlacedBlock(
            block=self.block.translate(dx, dy),
            box=self.box.translate(dx, dy),
        )


def lay_out(
    block: MeasuredBlock,
    canvas: Canvas,
    options: LayoutOptions,
    ctx: ResolutionContext,
) -> PlacedBlock:
    """Position a measured block on the canvas per alignment, margins and bias."""
    margin = options.margin.resolve(ctx)

    if options.align is TextAlign.LEFT:
        x = margin.left
    elif options.align is TextAlign.RIGHT:
        x = canvas.width - block.width - margin.right
    else:
        x = (canvas.width - block.width) / 2.0
    x = max(margin.left, min(x, canvas.width - block.width - margin.right))

    y = (canvas.height - block.height) * options.vertical_bias
    y = max(margin.top, min(y, canvas.height - block.height - margin.bottom))

    placed = block.translate(x, y)
    return PlacedBlock(
        block=placed,
        box=Box.from_xywh(x, y, block.width, block.height),
    )


class LayoutEngine:
    """Measure → wrap → position a caption block in one call."""

    def __init__(self, measurer: TextMeasurer | None = None) -> None:
        self.measurer = measurer or TextMeasurer()

    def layout(
        self,
        text: str,
        style: TextStyle,
        ctx: ResolutionContext,
        canvas: Canvas,
        *,
        options: LayoutOptions | None = None,
    ) -> PlacedBlock:
        options = options or LayoutOptions()
        block = self.measurer.measure(
            text, style, ctx, max_width=options.max_width
        )
        return lay_out(block, canvas, options, ctx)

    def layout_words(
        self,
        words: tuple[str, ...] | list[str],
        style: TextStyle,
        ctx: ResolutionContext,
        canvas: Canvas,
        *,
        options: LayoutOptions | None = None,
    ) -> PlacedBlock:
        options = options or LayoutOptions()
        block = self.measurer.measure_words(
            words, style, ctx, max_width=options.max_width
        )
        return lay_out(block, canvas, options, ctx)
