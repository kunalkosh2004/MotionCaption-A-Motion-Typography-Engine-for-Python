import pytest

from motion_caption import (
    Color,
    EmphasisMode,
    FontManager,
    TextStyle,
    ThemeSpec,
    load_theme,
    resolve_theme,
)
from motion_caption.themes import (
    THEME_REGISTRY,
    EmphasisAppearance,
    builtin_themes,
)
from motion_caption.typography.fonts import FontCatalog


class TestThemeSpec:
    def test_defaults(self):
        spec = ThemeSpec(name="t")
        assert spec.font_stack
        assert isinstance(spec.style, TextStyle)
        assert spec.animation.pop_ease.kind == "spring"
        assert spec.emphasis == {}

    def test_style_coerced_from_dict(self):
        spec = ThemeSpec(
            name="t",
            style={"size": "64px", "fill": {"color": "#FFD400"}, "uppercase": True},
        )
        assert spec.style.size.value == 64
        assert spec.style.fill.color == Color("#FFD400")
        assert spec.style.uppercase is True

    def test_animation_from_dict(self):
        spec = ThemeSpec(name="t", animation={"in_ease": "spring", "pop_ease": "bounce"})
        assert spec.animation.in_ease.kind == "spring"
        assert spec.animation.pop_ease.kind == "bounce"

    def test_emphasis_keyed_by_mode_strings(self):
        spec = ThemeSpec(
            name="t",
            emphasis={"high": {"color": "#FFD400", "scale": 1.25}, "karaoke": {"color": "#FFFFFF"}},
        )
        assert list(spec.emphasis) == [EmphasisMode.HIGH, EmphasisMode.KARAOKE]
        assert spec.emphasis[EmphasisMode.HIGH].scale == 1.25

    def test_emphasis_appearance_constraints(self):
        with pytest.raises(ValueError):
            EmphasisAppearance(scale=0)
        with pytest.raises(ValueError):
            EmphasisAppearance(weight=0)

    def test_serialization_round_trip(self):
        spec = load_theme("music_video")
        restored = ThemeSpec.model_validate_json(spec.model_dump_json())
        assert restored == spec


class TestBuiltinCatalog:
    def test_builtin_names(self):
        assert set(builtin_themes()) == {"clean", "music_video", "cinematic", "sport", "news"}

    def test_load_each_builtin(self):
        for name in builtin_themes():
            spec = load_theme(name)
            assert spec.name == name
            assert spec.display_name
            assert spec.description
            assert spec.font_stack
            assert spec.style.fill is not None

    def test_default_alias(self):
        assert load_theme("clean").name == "clean"

    def test_registered_in_registry(self):
        for name in builtin_themes():
            assert name in THEME_REGISTRY

    def test_unknown_theme_raises(self):
        with pytest.raises(KeyError, match="no theme registered"):
            load_theme("does-not-exist")

    def test_themes_have_distinct_personalities(self):
        assert load_theme("music_video").animation.in_ease.kind == "spring"
        assert load_theme("sport").animation.in_ease.kind == "overshoot"
        assert str(load_theme("clean").animation.in_ease) == "ease-out"

    def test_plugin_registration(self):
        name = "custom_theme"
        custom = ThemeSpec(name=name, style={"fill": {"color": "#00FF00"}})
        THEME_REGISTRY.add(name, custom)
        assert load_theme(name) is custom


class TestResolveTheme:
    def test_resolve_with_empty_catalog(self, tmp_path):
        manager = FontManager(FontCatalog(directories=[tmp_path]))
        resolved = resolve_theme(load_theme("clean"), font_manager=manager)
        assert resolved.fonts == ()
        assert resolved.base_style.font == load_theme("clean").font_stack

    def test_resolve_injects_font_stack_into_style(self, font_manager):
        resolved = resolve_theme(load_theme("music_video"), font_manager=font_manager)
        assert [r.family for r in resolved.base_style.font.fonts] == [
            "Avenir Next",
            "Avenir",
            "Helvetica Neue",
            "Helvetica",
            "Kohinoor Devanagari",
            "Mukta Mahee",
        ]

    def test_resolve_compiles_all_roles(self, font_manager):
        resolved = resolve_theme(load_theme("sport"), font_manager=font_manager)
        assert set(resolved.easings) == {"in", "out", "pop", "idle"}
        for fn in resolved.easings.values():
            assert fn(0.0) == pytest.approx(0.0, abs=1e-6)
            assert fn(1.0) == pytest.approx(1.0, abs=1e-2)

    def test_sport_stack_includes_indic_fallbacks(self, font_manager):
        resolved = resolve_theme(load_theme("sport"), font_manager=font_manager)
        assert [ref.family for ref in resolved.base_style.font.fonts][-2:] == [
            "Kohinoor Devanagari",
            "Mukta Mahee",
        ]

    def test_gurmukhi_word_resolves_via_fallback(self, font_manager):
        from motion_caption.models.units import Resolution, ResolutionContext
        from motion_caption.typography.measure import TextMeasurer

        resolved = resolve_theme(load_theme("sport"), font_manager=font_manager)
        block = TextMeasurer(font_manager).measure(
            "ਤਾਈ",
            resolved.base_style,
            ResolutionContext(canvas=Resolution(width=1080, height=1920)),
        )
        word = block.lines[0].words[0]
        assert word.text == "ਤਾਈ"
        assert "Mukta" in word.font_path

    def test_resolve_keeps_emphasis(self, font_manager):
        resolved = resolve_theme(load_theme("music_video"), font_manager=font_manager)
        high = resolved.emphasis[EmphasisMode.HIGH]
        assert high.scale > 1.0
        assert high.glow is not None

    def test_resolve_does_not_mutate_spec(self, font_manager):
        spec = load_theme("cinematic")
        before = spec.model_dump()
        resolve_theme(spec, font_manager=font_manager)
        assert spec.model_dump() == before
