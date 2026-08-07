import pytest

from motion_caption.models.units import Length


class TestBasicMeasurement:
    def test_single_line(self, measurer, style, ctx):
        block = measurer.measure("Hello world", style, ctx)
        assert block.line_count == 1
        assert block.width > 0
        assert block.height > 0
        assert block.lines[0].text == "Hello world"

    def test_word_boxes_are_ordered(self, measurer, style, ctx):
        block = measurer.measure("Hello world", style, ctx)
        first, second = block.lines[0].words
        assert first.box.left < second.box.left
        assert first.text == "Hello"
        assert second.text == "world"

    def test_empty_text(self, measurer, style, ctx):
        block = measurer.measure("   ", style, ctx)
        assert block.line_count == 0
        assert block.width == 0


class TestWrapping:
    def test_wrap_creates_lines(self, measurer, style, ctx):
        text = "This is a fairly long subtitle line that must wrap."
        block = measurer.measure(text, style, ctx, max_width=Length(400))
        assert block.line_count > 1
        for line in block.lines:
            assert line.width <= 400

    def test_wrapped_lines_join_to_text(self, measurer, style, ctx):
        text = "one two three four five six seven"
        block = measurer.measure(text, style, ctx, max_width=Length(300))
        assert block.text.replace("\n", " ") == text

    def test_no_max_width_is_single_line(self, measurer, style, ctx):
        block = measurer.measure("a b c d e f g h i j", style, ctx)
        assert block.line_count == 1

    def test_narrow_width_breaks_words_per_line(self, measurer, style, ctx):
        block = measurer.measure("alpha beta gamma", style, ctx, max_width=Length(90))
        assert block.line_count >= 2


class TestTypographyKnobs:
    def test_letter_spacing_increases_width(self, measurer, style, ctx):
        plain = measurer.measure("Hello", style, ctx).width
        spaced = measurer.measure(
            "Hello", style.model_copy(update={"letter_spacing": Length(10)}), ctx
        ).width
        assert spaced > plain

    def test_word_spacing_increases_line_width(self, measurer, style, ctx):
        plain = measurer.measure("Hello world", style, ctx).width
        spaced = measurer.measure(
            "Hello world", style.model_copy(update={"word_spacing": Length(20)}), ctx
        ).width
        assert spaced > plain

    def test_uppercase_transform(self, measurer, style, ctx):
        styled = style.model_copy(update={"uppercase": True})
        block = measurer.measure("hello world", styled, ctx)
        assert block.lines[0].text == "HELLO WORLD"

    def test_size_scales_width(self, measurer, style, ctx):
        small = measurer.measure("Hello", style, ctx).width
        big = measurer.measure("Hello", style.model_copy(update={"size": Length(96)}), ctx).width
        assert big > small


class TestResolutionIndependence:
    def test_same_design_units_different_canvas(self, measurer, style):
        from motion_caption import Resolution, ResolutionContext

        hd = ResolutionContext(canvas=Resolution(width=1920, height=1080))
        uhd = ResolutionContext(canvas=Resolution(width=3840, height=2160))
        a = measurer.measure("Hello world", style, hd)
        b = measurer.measure("Hello world", style, uhd)
        # FreeType hinting introduces slight non-linearity; allow a small margin.
        assert b.width == pytest.approx(2 * a.width, rel=0.05)

    def test_em_units_follow_font_size(self, measurer, style, ctx):
        styled = style.model_copy(update={"line_height": Length("2em")})
        block = measurer.measure("Hi", styled, ctx)
        assert block.lines[0].height == pytest.approx(96.0)


class TestCaching:
    def test_repeated_measurement_is_cached_and_equal(self, measurer, style, ctx):
        a = measurer.measure("cached text", style, ctx)
        b = measurer.measure("cached text", style, ctx)
        assert a == b
        assert len(measurer._measure_cache) == 1

    def test_different_inputs_do_not_collide(self, measurer, style, ctx):
        measurer.measure("alpha", style, ctx)
        measurer.measure("beta", style, ctx)
        assert len(measurer._measure_cache) == 2
