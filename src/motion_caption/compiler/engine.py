"""The Compiler: CaptionRequest -> SubtitleTimeline.

A deterministic frontend that runs the pure pipeline stages over a request and
caches the resulting timeline keyed by the request's canonical JSON. Identical
requests return byte-identical timelines; the cache never affects results.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict

from motion_caption.compiler.cache import CompiledThemeCache
from motion_caption.compiler.context import CompileContext
from motion_caption.compiler.resolve import design_context
from motion_caption.compiler.stages import PIPELINE
from motion_caption.ir.request import CaptionRequest
from motion_caption.ir.timeline import SubtitleTimeline
from motion_caption.typography.fonts import FontManager, default_font_manager


class Compiler:
    """Composition root: compiles ``CaptionRequest`` into ``SubtitleTimeline``."""

    def __init__(self, *, font_manager: FontManager | None = None, cache_size: int = 64) -> None:
        self.fonts = font_manager or default_font_manager()
        self._cache: OrderedDict[str, SubtitleTimeline] = OrderedDict()
        self._cache_size = cache_size
        self._theme_cache = CompiledThemeCache()

    @staticmethod
    def _key(request: CaptionRequest) -> str:
        digest = hashlib.sha256()
        digest.update(request.model_dump_json().encode("utf-8"))
        return digest.hexdigest()

    def compile(self, request: CaptionRequest) -> SubtitleTimeline:
        key = self._key(request)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        timeline = self._compile_fresh(request)
        self._cache[key] = timeline
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return timeline

    def _compile_fresh(self, request: CaptionRequest) -> SubtitleTimeline:
        design_ctx, canvas = design_context(request)
        ctx = CompileContext(
            request=request,
            fonts=self.fonts,
            design_ctx=design_ctx,
            canvas=canvas,
            theme_cache=self._theme_cache,
        )
        for stage in PIPELINE:
            stage(ctx)
        assert ctx.timeline is not None
        return ctx.timeline

    def invalidate(self) -> None:
        self._cache.clear()
        self._theme_cache.invalidate()


_DEFAULT_COMPILER: Compiler | None = None


def default_compiler() -> Compiler:
    """A process-wide shared Compiler (lazy singleton, cache included)."""
    global _DEFAULT_COMPILER
    if _DEFAULT_COMPILER is None:
        _DEFAULT_COMPILER = Compiler()
    return _DEFAULT_COMPILER


def compile(request: CaptionRequest) -> SubtitleTimeline:
    """Compile a request through the default compiler."""
    return default_compiler().compile(request)
