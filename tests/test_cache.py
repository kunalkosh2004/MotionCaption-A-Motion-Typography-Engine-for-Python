"""Tests for composition-boundary caches (CompiledThemeCache)."""

from __future__ import annotations

import pytest

from motion_caption.compiler import CompiledThemeCache, Compiler
from motion_caption.ir import CaptionRequest
from motion_caption.models.transcript import EmphasisMode, Transcript, WordTimestamp
from motion_caption.themes.spec import ThemeSpec
from motion_caption.typography.fonts import FontCatalog, FontManager, FontRef, FontStack


def _theme(any_font) -> ThemeSpec:
    return ThemeSpec(
        name="cache_test",
        font_stack=FontStack(fonts=[FontRef(family=any_font.family, weight=any_font.weight)]),
        style={"size": "48px", "fill": {"color": "#FFFFFF"}},
        emphasis={EmphasisMode.HIGH: {"scale": 1.2}},
    )


def _transcript() -> Transcript:
    return Transcript(
        words=[
            WordTimestamp(text="Hello", start=0.0, end=0.8),
            WordTimestamp(text="world", start=0.9, end=1.7),
        ]
    )


@pytest.fixture
def theme(any_font) -> ThemeSpec:
    return _theme(any_font)


@pytest.fixture
def compiler() -> Compiler:
    return Compiler()


def _request(theme, **overrides) -> CaptionRequest:
    data = {"transcript": _transcript(), "theme": theme}
    data.update(overrides)
    return CaptionRequest(**data)


class TestCompiledThemeCache:
    def test_returns_same_object_for_same_spec(self, any_font):
        cache = CompiledThemeCache()
        spec = _theme(any_font)
        fonts = FontManager()
        assert cache.resolve(spec, fonts) is cache.resolve(spec, fonts)

    def test_managers_over_same_catalog_share_entries(self, any_font):
        cache = CompiledThemeCache()
        spec = _theme(any_font)
        assert cache.resolve(spec, FontManager()) is cache.resolve(spec, FontManager())

    def test_distinct_catalogs_not_shared(self, any_font, tmp_path):
        cache = CompiledThemeCache()
        spec = _theme(any_font)
        custom = FontManager(catalog=FontCatalog([tmp_path]))
        assert cache.resolve(spec, FontManager()) is not cache.resolve(spec, custom)

    def test_distinct_specs_not_shared(self, any_font):
        cache = CompiledThemeCache()
        fonts = FontManager()
        a = cache.resolve(_theme(any_font), fonts)
        other = _theme(any_font).model_copy(update={"name": "cache_test_other"})
        b = cache.resolve(other, fonts)
        assert a is not b

    def test_invalidate(self, any_font):
        cache = CompiledThemeCache()
        spec = _theme(any_font)
        fonts = FontManager()
        first = cache.resolve(spec, fonts)
        cache.invalidate()
        assert cache.resolve(spec, fonts) is not first


class TestCompilerThemeCache:
    def test_theme_resolved_once_across_compiles(self, theme, compiler, monkeypatch):
        import motion_caption.compiler.cache as cache_module

        calls: list = []
        original = cache_module.resolve_theme

        def spy(spec, fonts):
            calls.append(spec)
            return original(spec, fonts)

        monkeypatch.setattr(cache_module, "resolve_theme", spy)
        # different metadata → timeline cache misses, theme cache should hit
        compiler.compile(_request(theme, metadata={"i": 1}))
        compiler.compile(_request(theme, metadata={"i": 2}))
        assert len(calls) == 1

    def test_theme_resolution_deterministic_with_cache(self, theme, compiler):
        # future_extensions never reaches the timeline, so these two requests
        # exercise a cache miss on the timeline but share the resolved theme.
        a = compiler.compile(_request(theme, future_extensions={"i": 1})).model_dump_json()
        b = compiler.compile(_request(theme, future_extensions={"i": 2})).model_dump_json()
        assert a == b

    def test_invalidate_forces_reresolve(self, theme, compiler, monkeypatch):
        import motion_caption.compiler.cache as cache_module

        calls: list = []
        original = cache_module.resolve_theme

        def spy(spec, fonts):
            calls.append(spec)
            return original(spec, fonts)

        monkeypatch.setattr(cache_module, "resolve_theme", spy)
        compiler.compile(_request(theme))
        compiler.invalidate()
        compiler.compile(_request(theme))
        assert len(calls) == 2
