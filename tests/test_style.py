from motion_caption.models.color import FillKind
from motion_caption.models.units import Length
from motion_caption.typography.style import (
    BackgroundSpec,
    GlowSpec,
    ShadowSpec,
    StrokeSpec,
    TextAlign,
    TextStyle,
)


class TestTextStyle:
    def test_defaults(self):
        style = TextStyle()
        assert style.size == Length(56)
        assert style.fill.kind is FillKind.SOLID
        assert style.align is TextAlign.CENTER
        assert not style.uppercase

    def test_opacity_bounds(self):
        try:
            TextStyle(opacity=1.5)
        except Exception:
            pass
        else:
            raise AssertionError("opacity must be clamped to 0..1")

    def test_json_round_trip(self):
        style = TextStyle(size="64px", letter_spacing="2px", stroke=StrokeSpec(width="3px"))
        restored = TextStyle.model_validate_json(style.model_dump_json())
        assert restored == style

    def test_effects_optional_by_default(self):
        style = TextStyle()
        assert style.stroke is None
        assert style.shadow is None
        assert style.glow is None
        assert style.background is None

    def test_full_treatment(self):
        style = TextStyle(
            size="72px",
            stroke=StrokeSpec(width="4px", opacity=0.9),
            shadow=ShadowSpec(),
            glow=GlowSpec(),
            background=BackgroundSpec(),
            uppercase=True,
        )
        assert style.stroke is not None
        assert style.background is not None

    def test_length_fields_accept_strings(self):
        style = TextStyle(size="1em", letter_spacing="2px", line_height="1.4em")
        assert style.size.value == 1.0
        assert style.size.unit.value == "em"
        assert style.line_height.unit.value == "em"
