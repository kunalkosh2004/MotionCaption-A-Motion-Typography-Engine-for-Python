import pytest

from motion_caption import (
    Canvas,
    Length,
    Padding,
    Resolution,
    ResolutionContext,
    TextAlign,
)
from motion_caption.layout import LayoutEngine, LayoutOptions, lay_out
from motion_caption.typography.measure import MeasuredBlock

CANVAS = Canvas(width=1920, height=1080)
CTX = ResolutionContext(canvas=Resolution(width=1920, height=1080))


def _block(width: float, height: float) -> MeasuredBlock:
    return MeasuredBlock(lines=[], width=width, height=height)


class TestPositioning:
    def test_center_bottom_default(self):
        placed = lay_out(_block(500, 100), CANVAS, LayoutOptions(), CTX)
        assert placed.box.left == pytest.approx((1920 - 500) / 2)
        assert placed.box.bottom == pytest.approx(1080)
        assert placed.box.top == pytest.approx(1080 - 100)

    def test_align_left(self):
        placed = lay_out(_block(500, 100), CANVAS, LayoutOptions(align=TextAlign.LEFT), CTX)
        assert placed.box.left == pytest.approx(0)

    def test_align_right(self):
        placed = lay_out(_block(500, 100), CANVAS, LayoutOptions(align=TextAlign.RIGHT), CTX)
        assert placed.box.right == pytest.approx(1920)

    def test_margins_respected(self):
        options = LayoutOptions(margin=Padding.uniform(Length(20)))
        placed = lay_out(_block(500, 100), CANVAS, options, CTX)
        assert placed.box.left >= 20
        assert placed.box.top >= 20
        assert placed.box.right <= 1920 - 20
        assert placed.box.bottom <= 1080 - 20

    def test_vertical_bias_top(self):
        placed = lay_out(_block(500, 100), CANVAS, LayoutOptions(vertical_bias=0.0), CTX)
        assert placed.box.top == pytest.approx(0)

    def test_vertical_bias_middle(self):
        placed = lay_out(_block(500, 100), CANVAS, LayoutOptions(vertical_bias=0.5), CTX)
        assert placed.box.center_y == pytest.approx(1080 / 2)

    def test_block_larger_than_canvas_clamped(self):
        placed = lay_out(_block(3000, 2000), CANVAS, LayoutOptions(), CTX)
        assert placed.box.left == pytest.approx(0)
        assert placed.box.top == pytest.approx(0)

    def test_empty_block(self):
        placed = lay_out(_block(0, 0), CANVAS, LayoutOptions(), CTX)
        assert placed.width == 0
        assert placed.height == 0


class TestPlacedBlock:
    def test_translate_moves_box_and_words(self, measurer, style):
        engine = LayoutEngine(measurer)
        placed = engine.layout("Hello world", style, CTX, CANVAS)
        moved = placed.translate(10, -20)
        assert moved.box.left == pytest.approx(placed.box.left + 10)
        assert moved.box.top == pytest.approx(placed.box.top - 20)
        original_word = placed.block.lines[0].words[0].box
        moved_word = moved.block.lines[0].words[0].box
        assert moved_word.left == pytest.approx(original_word.left + 10)
        assert moved_word.top == pytest.approx(original_word.top - 20)


class TestLayoutEngine:
    def test_max_width_enforced(self, measurer, style):
        engine = LayoutEngine(measurer)
        placed = engine.layout("a ".join(["word"] * 40), style, CTX, CANVAS)
        assert placed.width <= 0.85 * 1920 + 0.01

    def test_word_boxes_absolute(self, measurer, style):
        engine = LayoutEngine(measurer)
        placed = engine.layout("alpha beta", style, CTX, CANVAS)
        word = placed.block.lines[0].words[0]
        assert word.box.left == pytest.approx(placed.box.left)
        assert word.box.top == pytest.approx(placed.box.top)

    def test_layout_words(self, measurer, style):
        engine = LayoutEngine(measurer)
        placed = engine.layout_words(["one", "two"], style, CTX, CANVAS)
        assert placed.box.width > 0
