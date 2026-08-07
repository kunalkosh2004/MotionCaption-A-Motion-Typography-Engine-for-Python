import pytest

from motion_caption.typography.fonts import (
    FontCatalog,
    FontRef,
    FontStack,
    default_font_directories,
)


class TestFontCatalog:
    def test_default_directories_exist_on_this_platform(self):
        assert len(default_font_directories()) > 0

    def test_indexes_fonts(self, font_manager):
        assert len(font_manager.catalog.families()) > 0
        assert len(font_manager.catalog.all()) > 0

    def test_find_exact_family(self, font_manager, any_font):
        found = font_manager.catalog.find(any_font.family)
        assert found is not None
        assert found.family.lower() == any_font.family.lower()

    def test_find_case_insensitive(self, font_manager, any_font):
        assert font_manager.catalog.find(any_font.family.lower()) is not None

    def test_find_weight_matching(self, font_manager, any_font):
        bold = font_manager.catalog.find(any_font.family, 700)
        assert bold is None or abs(bold.weight - 700) <= abs(any_font.weight - 700)

    def test_unknown_family_returns_none(self, font_manager):
        assert font_manager.catalog.find("Definitely Not A Real Family XYZ") is None

    def test_custom_directory(self, tmp_path):
        catalog = FontCatalog(directories=[tmp_path])
        assert catalog.all() == []


class TestFontManager:
    def test_resolve_unknown_returns_none(self, font_manager):
        assert font_manager.resolve(FontRef(family="Not A Real Font ABC")) is None

    def test_resolve_stack_skips_missing(self, font_manager, any_font):
        stack = FontStack(
            fonts=[
                FontRef(family="Not A Real Font ABC"),
                FontRef(family=any_font.family),
            ]
        )
        resolved = font_manager.resolve_stack(stack)
        assert len(resolved) == 1
        assert resolved[0].family == any_font.family

    def test_glyph_coverage(self, font_manager, any_font):
        assert font_manager.glyph_supported(any_font, "A")
        assert font_manager.glyph_supported(any_font, " ")

    def test_measurement_and_metrics(self, font_manager, any_font):
        assert font_manager.text_width(any_font, 48, "Hello") > 0
        spaced = font_manager.text_width(any_font, 48, "Hello", tracking=10)
        assert spaced > font_manager.text_width(any_font, 48, "Hello")
        ascent, descent = font_manager.metrics(any_font, 48)
        assert ascent > 0
        assert descent > 0


class TestFontStackModel:
    def test_string_coercion(self):
        stack = FontStack(fonts=["Inter", "Helvetica"])
        assert [ref.family for ref in stack.fonts] == ["Inter", "Helvetica"]

    def test_len_and_bool(self):
        assert len(FontStack()) == 0
        assert not FontStack()
        assert FontStack(fonts=["X"])

    def test_frozen(self, any_font):
        from pydantic import ValidationError

        ref = FontRef(family=any_font.family)
        with pytest.raises(ValidationError):
            ref.family = "Other"
