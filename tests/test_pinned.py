"""Sanity checks for the pinned-font harness.

Golden frames and snapshots are only trustworthy if the pinned font
resolves to the exact bundled file on every machine. These tests pin that
assumption; if they fail, every snapshot/golden test is suspect.
"""

from __future__ import annotations

import pinned
from motion_caption.compiler.engine import Compiler
from motion_caption.models.units import Resolution, ResolutionContext
from motion_caption.themes.spec import ResolvedTheme
from motion_caption.typography.fonts import FontManager, FontRef


def test_pinned_font_file_exists() -> None:
    assert pinned.ROBOTO_PATH.is_file()
    assert pinned.ROBOTO_PATH.stat().st_size > 10_000


def test_pinned_manager_resolves_bundled_roboto(pinned_font_manager: FontManager) -> None:
    face = pinned_font_manager.resolve(pinned.pinned_font_ref())
    assert face is not None
    assert face.family == "Roboto"
    assert face.subfamily == "Regular"
    assert str(face.path) == str(pinned.ROBOTO_PATH)


def test_pinned_theme_binds_roboto(pinned_theme: ResolvedTheme) -> None:
    assert pinned_theme.fonts
    assert all(face.family == "Roboto" for face in pinned_theme.fonts)
    ctx = ResolutionContext(canvas=Resolution(width=1920, height=1080))
    assert pinned_theme.base_style.size.resolve(ctx) == 56


def test_pinned_compiler_is_deterministic(pinned_compiler: Compiler) -> None:
    from motion_caption.ir.request import CaptionRequest
    from motion_caption.models.transcript import Transcript, WordTimestamp

    words = [
        WordTimestamp(text=t, start=i, end=i + 0.8)
        for i, t in enumerate(["hello", "pinned", "world"])
    ]
    request = CaptionRequest(
        metadata={"source": "test_pinned"},
        transcript=Transcript(words=words),
        theme=pinned.pinned_theme_spec(),
    )
    first = pinned_compiler.compile(request)
    second = pinned_compiler.compile(request)
    assert first.model_dump_json() == second.model_dump_json()
    assert [word.text for word in first.words] == ["hello", "pinned", "world"]


def test_pinned_helpers_have_no_pytest_dependency() -> None:
    # The benchmark script reuses these helpers outside pytest.
    assert isinstance(pinned.pinned_font_ref(), FontRef)


def test_font_readers_are_closed_after_metadata_and_cmap(monkeypatch) -> None:
    """fontTools lazy readers must release their file handles (no leaks).

    The golden harness surfaces unclosed-file ``ResourceWarning``s at teardown;
    this pins the fix: every lazy ``TTFont`` opened for metadata or glyph
    coverage is closed once extraction completes.
    """
    from fontTools.ttLib import TTFont

    from motion_caption.typography.fonts import _codepoints, _load_font_metadata

    # Force fresh reader creation (the metadata/cmap caches are keyed by path).
    _load_font_metadata.cache_clear()
    _codepoints.cache_clear()

    closed: list[TTFont] = []
    original_close = TTFont.close

    def tracking_close(self: TTFont) -> None:
        closed.append(self)
        original_close(self)

    monkeypatch.setattr(TTFont, "close", tracking_close)

    manager = pinned.pinned_font_manager()
    face = manager.resolve(pinned.pinned_font_ref())
    assert face is not None
    assert manager.glyph_supported(face, "A") is True

    assert len(closed) >= 2, "metadata and cmap readers were not both closed"
