import pytest

from motion_caption.models.color import Color, FillKind, FillSpec, GradientFill, GradientStop


class TestColorConstruction:
    def test_hex(self):
        assert Color("#ff0000").rgba == (255, 0, 0, 255)

    def test_short_hex(self):
        assert Color("#f0f").rgba == (255, 0, 255, 255)

    def test_hex_with_alpha(self):
        assert Color("#ff000080").a == 128

    def test_rgba_function(self):
        assert Color("rgba(255, 0, 0, 0.5)").rgba == (255, 0, 0, 128)

    def test_tuple(self):
        assert Color((0, 255, 0)).rgba == (0, 255, 0, 255)

    def test_named_channels(self):
        assert Color(r=1, g=2, b=3).rgba == (1, 2, 3, 255)

    def test_invalid(self):
        with pytest.raises(ValueError):
            Color("not-a-color")


class TestColorBehavior:
    def test_hex_properties(self):
        assert Color("#ff0000").hex == "#FF0000"
        assert Color("#ff000080").hex_with_alpha == "#FF000080"

    def test_ass_encoding(self):
        assert Color("#ff0000").as_ass() == "&HFF0000FF"  # red  → &H AABBGGRR
        assert Color("#0000ff").as_ass() == "&HFFFF0000"  # blue → &H AA BB GG RR

    def test_ass_alpha(self):
        assert Color("#ffffff").ass_alpha == "00"
        assert Color(r=255, g=255, b=255, a=0).ass_alpha == "FF"

    def test_interpolate_midpoint(self):
        black = Color("#000000")
        white = Color("#ffffff")
        assert black.interpolate(white, 0.5).rgba == (128, 128, 128, 255)

    def test_luminance(self):
        assert Color("#ffffff").luminance == pytest.approx(1.0)
        assert Color("#000000").luminance == pytest.approx(0.0)


class TestGradient:
    def test_sample_midpoint(self):
        gradient = GradientFill(
            stops=[GradientStop(color=Color("#000000"), position=0.0),
                   GradientStop(color=Color("#ffffff"), position=1.0)]
        )
        assert gradient.sample(0.5).rgba == (128, 128, 128, 255)

    def test_clamps_outside_range(self):
        gradient = GradientFill(stops=[GradientStop(color=Color("#000000"), position=0.0),
                                      GradientStop(color=Color("#ffffff"), position=1.0)])
        assert gradient.sample(-1).hex == "#000000"
        assert gradient.sample(2).hex == "#FFFFFF"

    def test_unsorted_stops(self):
        gradient = GradientFill(
            stops=[GradientStop(color=Color("#ffffff"), position=1.0),
                   GradientStop(color=Color("#000000"), position=0.0)]
        )
        assert gradient.sample(0.5).rgba == (128, 128, 128, 255)

    def test_single_stop_is_solid(self):
        gradient = GradientFill(stops=[GradientStop(color=Color("#123456"))])
        assert gradient.is_solid
        assert gradient.sample(0.9).hex == "#123456"


class TestFillSpec:
    def test_default_is_white_solid(self):
        fill = FillSpec()
        assert fill.kind is FillKind.SOLID
        assert not fill.uses_gradient
