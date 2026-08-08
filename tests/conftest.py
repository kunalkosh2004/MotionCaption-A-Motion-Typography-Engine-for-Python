from __future__ import annotations

import pytest

import pinned
from motion_caption import Resolution, ResolutionContext, TextMeasurer, TextStyle
from motion_caption.compiler.engine import Compiler
from motion_caption.themes.spec import ResolvedTheme, ThemeSpec
from motion_caption.typography.fonts import FontManager, FontRef, FontStack


@pytest.fixture(scope="session")
def font_manager() -> FontManager:
    return FontManager()


@pytest.fixture(scope="session")
def any_font(font_manager: FontManager):
    face = font_manager.catalog.find("Helvetica") or font_manager.catalog.find("Arial")
    if face is None:
        all_faces = font_manager.catalog.all()
        if not all_faces:
            pytest.skip("no system fonts available on this machine")
        face = all_faces[0]
    return face


@pytest.fixture
def style(any_font) -> TextStyle:
    return TextStyle(
        font=FontStack(fonts=[FontRef(family=any_font.family, weight=any_font.weight)]),
        size="48px",
    )


@pytest.fixture
def measurer() -> TextMeasurer:
    return TextMeasurer()


@pytest.fixture
def ctx() -> ResolutionContext:
    return ResolutionContext(canvas=Resolution(width=1920, height=1080))


# -- pinned-font harness -----------------------------------------------------


@pytest.fixture(scope="session")
def pinned_font_manager() -> FontManager:
    """Font resolution restricted to the bundled Roboto file."""
    return pinned.pinned_font_manager()


@pytest.fixture(scope="session")
def pinned_theme_spec() -> ThemeSpec:
    """The deterministic golden theme (path-bound Roboto + full feature set)."""
    return pinned.pinned_theme_spec()


@pytest.fixture(scope="session")
def pinned_theme(pinned_font_manager: FontManager) -> ResolvedTheme:
    return pinned.pinned_theme(pinned_font_manager)


@pytest.fixture(scope="session")
def pinned_compiler(pinned_font_manager: FontManager) -> Compiler:
    return pinned.pinned_compiler(pinned_font_manager)
