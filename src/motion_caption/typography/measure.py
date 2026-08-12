"""Deterministic text measurement and line wrapping.

A ``TextMeasurer`` resolves a ``TextStyle`` against a ``ResolutionContext``,
measures glyphs with Pillow (per-character advances + letter-spacing), picks a
per-word font via the fallback stack's glyph coverage, and greedily wraps
words into ``MeasuredBlock``. Everything is cached; identical inputs produce
identical numbers.
"""

from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache

from pydantic import BaseModel

from motion_caption.models.geometry import Box
from motion_caption.models.units import Length, ResolutionContext
from motion_caption.typography.fonts import (
    FontFile,
    FontManager,
    default_font_manager,
    font_resolution_diagnostic,
)
from motion_caption.typography.style import TextStyle


class MeasuredWord(BaseModel):
    """One measured word, positioned relative to its line's origin."""

    text: str
    box: Box
    advance: float
    font_path: str
    font_index: int = 0
    font_size: float

    @property
    def width(self) -> float:
        return self.box.width


class MeasuredLine(BaseModel):
    """One wrapped line of measured words."""

    words: list[MeasuredWord]
    width: float
    height: float
    ascent: float
    descent: float
    baseline: float

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    def translate(self, dx: float, dy: float) -> MeasuredLine:
        return MeasuredLine(
            words=[
                word.model_copy(update={"box": word.box.translate(dx, dy)})
                for word in self.words
            ],
            width=self.width,
            height=self.height,
            ascent=self.ascent,
            descent=self.descent,
            baseline=self.baseline,
        )


class MeasuredBlock(BaseModel):
    """A wrapped, measured text block."""

    lines: list[MeasuredLine]
    width: float
    height: float

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def translate(self, dx: float, dy: float) -> MeasuredBlock:
        return MeasuredBlock(
            lines=[line.translate(dx, dy) for line in self.lines],
            width=self.width,
            height=self.height,
        )


@lru_cache(maxsize=2048)
def _wrap_words(
    words: tuple[str, ...],
    files: tuple[FontFile, ...],
    manager: FontManager,
    size: int,
    tracking: float,
    word_spacing: float,
    line_height: float,
    max_width: float,
) -> tuple[tuple[tuple[str, float, float, str, int, int, int], ...], ...]:
    """Pure greedy wrapping. Returns raw tuples; models are built on the way out.

    Each word tuple is (text, x, width, font_path, font_index, ascent, descent).
    """

    def pick_font(word: str) -> FontFile:
        for face in files:
            if all(manager.glyph_supported(face, char) for char in word):
                return face
        # No single face covers every character: use the face that covers the
        # most glyphs so a word is never needlessly rendered with a font that
        # lacks its script (which would draw .notdef boxes).
        return max(
            files,
            key=lambda face: sum(manager.glyph_supported(face, char) for char in word),
        )

    space_width = manager.text_width(files[0], size, " ")
    gap = space_width + word_spacing

    lines: list[tuple[tuple[str, float, float, str, int, int, int], ...]] = []
    current: list[tuple[str, float, float, str, int, int, int]] = []
    cursor = 0.0

    for word in words:
        face = pick_font(word)
        width = manager.text_width(face, size, word, tracking)
        if current and cursor + width > max_width:
            lines.append(tuple(current))
            current = []
            cursor = 0.0
        x = cursor
        ascent, descent = manager.metrics(face, size)
        current.append((word, x, width, str(face.path), face.index, ascent, descent))
        cursor = x + width + gap

    if current:
        lines.append(tuple(current))
    return tuple(lines)


class TextMeasurer:
    """Measures and wraps text against a style and resolution context."""

    def __init__(self, fonts: FontManager | None = None, *, cache_size: int = 256) -> None:
        self.fonts = fonts or default_font_manager()
        self._cache_size = cache_size

    def measure(
        self,
        text: str,
        style: TextStyle,
        ctx: ResolutionContext,
        *,
        max_width: Length | None = None,
    ) -> MeasuredBlock:
        if style.uppercase:
            text = text.upper()
        words = tuple(text.split())
        if not words:
            return MeasuredBlock(lines=[], width=0.0, height=0.0)
        return self.measure_words(words, style, ctx, max_width=max_width)

    def measure_words(
        self,
        words: tuple[str, ...] | list[str],
        style: TextStyle,
        ctx: ResolutionContext,
        *,
        max_width: Length | None = None,
    ) -> MeasuredBlock:
        words = tuple(words)
        if not words:
            return MeasuredBlock(lines=[], width=0.0, height=0.0)

        files = self.fonts.resolve_stack(style.font)
        if not files:
            raise ValueError(font_resolution_diagnostic(style.font, []))

        size = round(style.size.resolve(ctx))
        if size <= 0:
            raise ValueError(f"font size must be positive, got {size}")

        text_ctx = ctx.model_copy(update={"font_size": float(size)})
        tracking = style.letter_spacing.resolve(text_ctx)
        word_spacing = style.word_spacing.resolve(text_ctx)
        line_height = style.line_height.resolve(text_ctx)
        max_width_px = max_width.resolve(text_ctx) if max_width is not None else float("inf")

        key = (
            words,
            tuple(files),
            self.fonts,
            size,
            round(tracking, 3),
            round(word_spacing, 3),
            round(line_height, 3),
            round(max_width_px, 3) if max_width_px != float("inf") else float("inf"),
        )
        block = self._cached(key)
        return block

    def _cached(self, key: tuple) -> MeasuredBlock:
        cache: OrderedDict = getattr(self, "_measure_cache", None)
        if cache is None:
            cache = OrderedDict()
            object.__setattr__(self, "_measure_cache", cache)
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        block = self._build(*key)
        cache[key] = block
        if len(cache) > self._cache_size:
            cache.popitem(last=False)
        return block

    def _build(
        self,
        words: tuple[str, ...],
        files: tuple[FontFile, ...],
        manager: FontManager,
        size: int,
        tracking: float,
        word_spacing: float,
        line_height: float,
        max_width: float,
    ) -> MeasuredBlock:
        raw_lines = _wrap_words(
            words, files, manager, size, tracking, word_spacing, line_height, max_width
        )
        lines: list[MeasuredLine] = []
        block_width = 0.0
        for raw_line in raw_lines:
            line_height_px = max(
                line_height,
                max(a + d for (_, _, _, _, _, a, d) in raw_line),
            )
            first_word = raw_line[0]
            ascent, descent = first_word[5], first_word[6]
            measured_words = []
            line_width = 0.0
            for text, x, width, path, index, _, _ in raw_line:
                line_width = max(line_width, x + width)
                measured_words.append(
                    MeasuredWord(
                        text=text,
                        box=Box(left=x, top=0.0, right=x + width, bottom=line_height_px),
                        advance=width,
                        font_path=path,
                        font_index=index,
                        font_size=float(size),
                    )
                )
            lines.append(
                MeasuredLine(
                    words=measured_words,
                    width=line_width,
                    height=line_height_px,
                    ascent=ascent,
                    descent=descent,
                    baseline=ascent,
                )
            )
            block_width = max(block_width, line_width)
        return MeasuredBlock(
            lines=lines,
            width=block_width,
            height=sum(line.height for line in lines),
        )
