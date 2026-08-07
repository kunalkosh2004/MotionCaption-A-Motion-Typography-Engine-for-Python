import pytest

from motion_caption.models.units import (
    DesignSpace,
    Length,
    Resolution,
    ResolutionContext,
    ScalePolicy,
    Unit,
)


class TestLengthConstruction:
    def test_number_is_pixels(self):
        assert Length(12) == Length(value=12.0, unit=Unit.PX)

    def test_css_strings(self):
        assert Length("1.5em").unit is Unit.EM
        assert Length("1.5em").value == 1.5
        assert Length("10%").unit is Unit.PERCENT
        assert Length("80vw").unit is Unit.VW
        assert Length("-4px").value == -4.0

    def test_kwargs_unit(self):
        assert Length(1.5, unit="em").unit is Unit.EM

    def test_dict_and_copy(self):
        assert Length({"value": 3, "unit": "vh"}) == Length(value=3.0, unit=Unit.VH)
        assert Length(Length(5)) == Length(5)

    def test_invalid(self):
        with pytest.raises(ValueError):
            Length("banana")


class TestLengthResolution:
    @pytest.fixture
    def ctx(self):
        return ResolutionContext(canvas=Resolution(width=1280, height=720))

    def test_px_scales_to_canvas(self, ctx):
        # 1280x720 is 2/3 of the 1920x1080 design space (COVER).
        assert Length(48).resolve(ctx) == pytest.approx(48 * (2 / 3))

    def test_em_requires_font_size(self, ctx):
        with pytest.raises(ValueError):
            Length("1.2em").resolve(ctx)

    def test_em_uses_font_size(self, ctx):
        sized = ctx.model_copy(update={"font_size": 100.0})
        assert Length("1.2em").resolve(sized) == pytest.approx(120.0)

    def test_percent_is_minor_dimension(self, ctx):
        assert Length("10%").resolve(ctx) == pytest.approx(0.1 * 1080 * (2 / 3))

    def test_vw_vh_are_canvas_relative(self, ctx):
        assert Length("100vw").resolve(ctx) == pytest.approx(1280.0)
        assert Length("50vh").resolve(ctx) == pytest.approx(360.0)

    def test_resolution_independent_scaling(self):
        small = ResolutionContext(canvas=Resolution(width=1280, height=720))
        big = ResolutionContext(canvas=Resolution(width=3840, height=2160))
        assert Length(48).resolve(big) == pytest.approx(3 * Length(48).resolve(small))


class TestScalePolicy:
    def test_cover(self):
        canvas = Resolution(width=1080, height=1920)
        ref = Resolution(width=1920, height=1080)
        assert ScalePolicy.COVER.scale(canvas, ref) == pytest.approx(1920 / 1080)

    def test_fit(self):
        canvas = Resolution(width=1080, height=1920)
        ref = Resolution(width=1920, height=1080)
        assert ScalePolicy.FIT.scale(canvas, ref) == pytest.approx(1080 / 1920)

    def test_none(self):
        assert ScalePolicy.NONE.scale(Resolution(500, 500), Resolution(1920, 1080)) == 1.0


class TestResolution:
    def test_aspect(self):
        assert Resolution(width=1920, height=1080).aspect == pytest.approx(16 / 9)

    def test_portrait(self):
        assert Resolution(width=1080, height=1920).is_portrait()
        assert not Resolution(width=1920, height=1080).is_portrait()

    def test_design_space_default(self):
        assert DesignSpace().reference == Resolution(width=1920, height=1080)
