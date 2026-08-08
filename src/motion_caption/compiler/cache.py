"""Caches at composition boundaries (never inside pure stages).

``resolve_theme`` re-resolves the font stack (a full directory scan on first
use) on every call; this cache makes repeated compiles of the same theme
cheap. It is an exact-key LRU — identical inputs return identical outputs, so
determinism is untouched.

The font half of the key is the *catalog's directory list* rather than the
manager's identity: two ``FontManager`` instances over the same directories
resolve identically, so they may share cache entries. Distinct catalogs get
distinct entries.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict

from motion_caption.themes.spec import ResolvedTheme, ThemeSpec, resolve_theme
from motion_caption.typography.fonts import FontManager


def _spec_digest(spec: ThemeSpec) -> str:
    digest = hashlib.sha256()
    digest.update(spec.model_dump_json().encode("utf-8"))
    return digest.hexdigest()


def _catalog_key(fonts: FontManager) -> tuple[str, ...]:
    return tuple(str(path) for path in fonts.catalog.directories)


class CompiledThemeCache:
    """LRU cache of resolved themes keyed by ``(spec digest, catalog dirs)``."""

    def __init__(self, size: int = 64) -> None:
        self._size = size
        self._entries: OrderedDict[tuple[str, tuple[str, ...]], ResolvedTheme] = OrderedDict()

    def resolve(self, spec: ThemeSpec, fonts: FontManager) -> ResolvedTheme:
        key = (_spec_digest(spec), _catalog_key(fonts))
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            return cached
        theme = resolve_theme(spec, fonts)
        self._entries[key] = theme
        if len(self._entries) > self._size:
            self._entries.popitem(last=False)
        return theme

    def invalidate(self) -> None:
        self._entries.clear()
