"""Regression tests for the bundled font fallback system.

These guard against the production bug where captions render as ``□`` boxes:
on a minimal Linux/Docker runtime the theme stacks (Helvetica, Arial, …) and
the ``DejaVu Sans`` fallback do not exist, so previously only the Indic
fallbacks resolved and English text was drawn with a Devanagari font that has
no Latin glyphs.

The bundled ``Noto Sans`` in the package guarantees a Latin-capable face
resolves on any runtime. The tests below run against a catalog restricted to
the bundled fonts — i.e. the same situation as a bare container.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageFont

from motion_caption import Canvas, TimelineRenderer, load_theme, resolve_theme
from motion_caption.compiler import Compiler
from motion_caption.ir import CaptionRequest
from motion_caption.models.transcript import Transcript, WordTimestamp
from motion_caption.typography.fonts import (
    FontCatalog,
    FontManager,
    bundled_font_directories,
    default_font_directories,
    font_resolution_diagnostic,
)
from motion_caption.typography.measure import TextMeasurer

BUNDLED_DIR = Path(bundled_font_directories()[0])

# The caption samples the tests must render as real glyphs: English, numbers,
# punctuation, apostrophes, common symbols, and Unicode where supported.
SAMPLES = (
    "Hello World 123!",
    "It's working! Let's test this.",
    "Café — résumé",
)


@pytest.fixture(scope="module")
def bundled_manager() -> FontManager:
    """A manager whose catalog is ONLY the bundled fonts directory.

    This mirrors a bare container (no system fonts) — the exact environment
    where the ``□`` bug occurred.
    """
    return FontManager(catalog=FontCatalog(bundled_font_directories()))


def _captions_in_frames(images: list[Image.Image]) -> int:
    """Non-transparent pixels across the rendered caption frames."""
    ink = 0
    for image in images:
        ink += sum(1 for *_, alpha in image.getdata() if alpha > 0)
    return ink


class TestBundledFontAsset:
    def test_bundle_directory_is_shipped(self):
        assert BUNDLED_DIR.is_dir()

    def test_regular_face_is_present_and_loadable(self):
        regular = BUNDLED_DIR / "NotoSans-Regular.ttf"
        assert regular.is_file()
        font = ImageFont.truetype(str(regular), size=48)
        assert font is not None

    def test_family_and_weights(self):
        from motion_caption.typography.fonts import _load_font_metadata

        faces = _load_font_metadata(str(BUNDLED_DIR / "NotoSans-Regular.ttf"))
        assert faces, "bundled font must parse"
        assert faces[0].family == "Noto Sans"
        assert faces[0].weight == 400

    def test_covers_all_sample_glyphs(self, bundled_manager):
        face = bundled_manager.catalog.find("Noto Sans")
        assert face is not None
        for sample in SAMPLES:
            unsupported = [c for c in sample if not bundled_manager.glyph_supported(face, c)]
            assert not unsupported, f"bundled font lacks glyphs for {sample!r}: {unsupported!r}"


class TestContainerLikeResolution:
    """The production regression: no system fonts, only the bundle."""

    @pytest.mark.parametrize("theme_name", ["clean", "cinematic", "music_video", "news", "sport"])
    def test_every_builtin_theme_resolves_a_latin_capable_base(self, bundled_manager, theme_name):
        theme = resolve_theme(load_theme(theme_name), font_manager=bundled_manager)
        assert theme.fonts, f"theme {theme_name} must resolve fonts in a bare environment"
        base = theme.fonts[0]
        assert all(
            bundled_manager.glyph_supported(base, char) for char in "Hello World 123!"
        ), (
            f"theme {theme_name} base font {base.family} cannot draw Latin text — "
            "this is the 'captions render as boxes' regression"
        )

    def test_default_directories_include_the_bundle(self):
        dirs = default_font_directories()
        assert any(Path(d) == BUNDLED_DIR for d in dirs)

    @pytest.mark.parametrize(
        "sample",
        SAMPLES,
        ids=["latin", "punctuation", "unicode"],
    )
    def test_compiled_words_use_a_font_that_covers_the_text(
        self, bundled_manager, sample
    ):
        compiled = Compiler(font_manager=bundled_manager).compile(_request(sample))
        assert compiled.words, "compile must produce words"
        for word in compiled.words:
            typography = word.typography
            assert typography is not None
            for char in word.text:
                assert typography.font.family == "Noto Sans"
                assert bundled_manager.glyph_supported(
                    _face(bundled_manager, typography.font.path), char
                ), f"font for {word.text!r} lacks glyph {char!r}"


def _request(text: str) -> CaptionRequest:
    words = []
    cursor = 0.0
    for token in text.split():
        words.append(WordTimestamp(text=token, start=cursor, end=cursor + 0.8))
        cursor += 1.0
    return CaptionRequest(transcript=Transcript(words=words))


def _face(manager: FontManager, path: str):
    from motion_caption.typography.fonts import _load_font_metadata

    return _load_font_metadata(path)[0]


class TestRenderReadableCaptions:
    @pytest.mark.parametrize(
        "sample",
        SAMPLES,
        ids=["latin", "punctuation", "unicode"],
    )
    def test_frames_contain_ink_for_the_text(self, bundled_manager, sample):
        compiled = Compiler(font_manager=bundled_manager).compile(_request(sample))
        # Render at the timeline's design resolution (the compiler lays out
        # against a 1920x1080 reference), so the text lands on-canvas.
        reference = compiled.design.reference
        frames = TimelineRenderer().render_sequence(
            compiled,
            Canvas(width=reference.width, height=reference.height),
            fps=4,
            start=0.0,
            end=1.5,
        )
        ink = _captions_in_frames(frames)
        assert ink > 2000, f"rendered caption {sample!r} produced too little ink ({ink})"

    def test_measurer_uses_covering_font(self, bundled_manager):
        """Mixed punctuation renders via the bundled Noto Sans, not a glyph-less
        face — the direct regression for tofu boxes in measurement."""
        measurer = TextMeasurer(bundled_manager)
        block = measurer.measure(
            "It's working!",
            _text_style(),
            _resolution_ctx(),
        )
        word = block.lines[0].words[0]
        assert Path(word.font_path).parent == BUNDLED_DIR


def _text_style():
    from motion_caption.typography.fonts import FontStack
    from motion_caption.typography.style import TextStyle

    return TextStyle(font=FontStack(fonts=["Noto Sans"]), size="48px")


def _resolution_ctx():
    from motion_caption import Resolution, ResolutionContext

    return ResolutionContext(canvas=Resolution(width=1280, height=720))


class TestDiagnostics:
    def test_font_resolution_diagnostic_is_actionable(self):
        from motion_caption.typography.fonts import FontStack

        message = font_resolution_diagnostic(FontStack(fonts=["Nope"]), [])
        assert "Caption font could not be loaded." in message
        assert "Requested font:" in message
        assert "Nope" in message
        assert "Resolved path:" in message
        assert "Environment:" in message
        assert "Available fallback:" in message

    def test_compiler_error_is_actionable(self, bundled_manager):
        manager = FontManager(catalog=FontCatalog([Path("definitely/missing")]))
        request = _request("Hello")
        with pytest.raises(ValueError) as exc:
            Compiler(font_manager=manager).compile(request)
        message = str(exc.value)
        assert "Caption font could not be loaded." in message
        assert "Requested font:" in message
