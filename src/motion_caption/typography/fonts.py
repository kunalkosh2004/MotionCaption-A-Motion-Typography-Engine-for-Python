"""Font discovery, fallback and loading.

Responsibility: resolve a ``FontStack`` (ordered, weighted font requests) into
concrete font files and cached Pillow font handles, with per-character glyph
coverage for accurate fallback. All font I/O is lazy and cached; nothing is
scanned at import time.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont
from pydantic import BaseModel, ConfigDict, Field, model_validator

# fonttools is used purely as a font metadata reader; silence its noisy
# timestamp/table warnings on legacy system fonts.
logging.getLogger("fontTools.ttLib").setLevel(logging.ERROR)

_FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}


def default_font_directories() -> list[Path]:
    """Platform-appropriate system font directories."""
    home = Path.home()
    if sys.platform == "darwin":
        return [
            Path("/System/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"),
            home / "Library" / "Fonts",
        ]
    if os.name == "nt":
        windir = Path(os.environ.get("WINDIR", "C:\\Windows"))
        return [windir / "Fonts", home / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"]
    return [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".fonts",
        home / ".local" / "share" / "fonts",
    ]


# Mapping from style keywords found in font names to CSS weight numbers.
_WEIGHT_BY_NAME: dict[str, int] = {
    "thin": 100,
    "hairline": 100,
    "extralight": 200,
    "ultralight": 200,
    "light": 300,
    "regular": 400,
    "book": 400,
    "normal": 400,
    "medium": 500,
    "semibold": 600,
    "demibold": 600,
    "bold": 700,
    "extrabold": 800,
    "ultrabold": 800,
    "black": 900,
    "heavy": 900,
}


def _weight_from_name(name: str) -> int:
    lowered = name.lower()
    for keyword, weight in _WEIGHT_BY_NAME.items():
        if keyword in lowered:
            return weight
    return 400


@dataclass(frozen=True, slots=True)
class FontFile:
    """A concrete font face inside a file."""

    path: Path
    index: int  # face index within TTC collections
    family: str
    subfamily: str
    weight: int
    italic: bool
    postscript_name: str

    @property
    def key(self) -> tuple[str, int]:
        return (str(self.path), self.index)


@lru_cache(maxsize=4096)
def _load_font_metadata(path: str) -> tuple[FontFile, ...]:
    """Parse font metadata for every face in a file. Cache-safe."""
    source = Path(path)
    if source.suffix.lower() == ".ttc":
        try:
            from fontTools.ttLib import TTCollection

            collection = TTCollection(str(source), lazy=True)
            faces = list(collection.fonts)
        except Exception:
            return ()
    else:
        try:
            from fontTools.ttLib import TTFont

            faces = [TTFont(str(source), lazy=True)]
        except Exception:
            return ()

    result: list[FontFile] = []
    for index, face in enumerate(faces):
        try:
            name_table = face["name"]
            family = (
                name_table.getDebugName(16)
                or name_table.getDebugName(1)
                or source.stem
            )
            subfamily = name_table.getDebugName(17) or name_table.getDebugName(2) or "Regular"
            weight = _weight_of(face, subfamily)
            italic = _italic_of(face, subfamily)
            postscript = name_table.getDebugName(6) or ""
        except Exception:
            continue
        result.append(
            FontFile(source, index, family, subfamily, weight, italic, postscript)
        )
    return tuple(result)


def _weight_of(face: object, subfamily: str) -> int:
    try:
        os2 = face.get("OS/2")
        if os2 is not None and os2.usWeightClass:
            return int(os2.usWeightClass)
    except Exception:
        pass
    return _weight_from_name(subfamily)


def _italic_of(face: object, subfamily: str) -> bool:
    try:
        os2 = face.get("OS/2")
        if os2 is not None:
            fs_selection = os2.fsSelection
            if fs_selection is not None and fs_selection & 0x01:
                return True
    except Exception:
        pass
    try:
        head = face.get("head")
        if head is not None and head.macStyle & 0x02:
            return True
    except Exception:
        pass
    return "italic" in subfamily.lower() or "oblique" in subfamily.lower()


class FontCatalog:
    """Indexes the fonts available in a set of directories.

    The index is built lazily on first lookup and cached for the catalog's
    lifetime. Matching is: exact family (case-insensitive), closest weight,
    preferred slant.
    """

    def __init__(self, directories: Sequence[str | Path] | None = None) -> None:
        source = default_font_directories() if directories is None else directories
        self.directories = [Path(d) for d in source]
        self._index: dict[str, list[FontFile]] | None = None

    def _ensure_indexed(self) -> None:
        if self._index is not None:
            return
        index: dict[str, list[FontFile]] = {}
        for directory in self.directories:
            if not directory.is_dir():
                continue
            for candidate in directory.rglob("*"):
                if candidate.suffix.lower() not in _FONT_SUFFIXES:
                    continue
                for face in _load_font_metadata(str(candidate)):
                    index.setdefault(face.family.lower(), []).append(face)
        self._index = index

    def all(self) -> list[FontFile]:
        self._ensure_indexed()
        return [face for faces in self._index.values() for face in faces]

    def families(self) -> list[str]:
        self._ensure_indexed()
        return sorted({face.family for faces in self._index.values() for face in faces})

    def find(
        self,
        family: str,
        weight: int = 400,
        *,
        italic: bool = False,
    ) -> FontFile | None:
        self._ensure_indexed()
        candidates = self._index.get(family.strip().lower())
        if not candidates:
            return None
        if italic:
            slanted = [f for f in candidates if f.italic]
            if slanted:
                candidates = slanted
        else:
            upright = [f for f in candidates if not f.italic]
            if upright:
                candidates = upright
        return min(
            candidates,
            key=lambda f: (abs(f.weight - weight), f.subfamily.lower() != "regular"),
        )


class FontStyle(StrEnum):
    NORMAL = "normal"
    ITALIC = "italic"


class FontRef(BaseModel):
    """A request for a font face: family, weight, slant, or an explicit file."""

    family: str
    weight: int = Field(default=400, ge=100, le=900, multiple_of=100)
    style: FontStyle = FontStyle.NORMAL
    path: str | None = None

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if isinstance(data, str):
            return {"family": data}
        if isinstance(data, FontRef):
            return data
        return data


class FontStack(BaseModel):
    """An ordered fallback chain of font requests."""

    fonts: list[FontRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if isinstance(data, str):
            return {"fonts": [FontRef(family=data)]}
        if isinstance(data, (list, tuple)):
            refs: list[FontRef] = []
            for ref in data:
                if isinstance(ref, FontRef):
                    refs.append(ref)
                elif isinstance(ref, dict):
                    refs.append(FontRef.model_validate(ref))
                else:
                    refs.append(FontRef(family=str(ref)))
            return {"fonts": refs}
        return data

    def __len__(self) -> int:
        return len(self.fonts)

    def __bool__(self) -> bool:
        return bool(self.fonts)


@lru_cache(maxsize=1024)
def _codepoints(path: str, index: int) -> frozenset[int]:
    """Glyph coverage for a font face, cached."""
    try:
        from fontTools.ttLib import TTFont

        face = TTFont(path, fontNumber=index, lazy=True)
        cmap = face.getBestCmap() or {}
        return frozenset(cmap.keys())
    except Exception:
        return frozenset()


class FontManager:
    """Resolves font requests and loads cached measurement handles."""

    def __init__(self, catalog: FontCatalog | None = None) -> None:
        self.catalog = catalog or FontCatalog()
        self._pil_fonts: dict[tuple[str, int, int], ImageFont.FreeTypeFont] = {}

    def resolve(self, ref: FontRef) -> FontFile | None:
        if ref.path:
            faces = _load_font_metadata(ref.path)
            if not faces:
                return None
            candidates = [f for f in faces if not f.italic] or list(faces)
            return min(candidates, key=lambda f: abs(f.weight - ref.weight))
        return self.catalog.find(ref.family, ref.weight, italic=ref.style is FontStyle.ITALIC)

    def resolve_stack(self, stack: FontStack) -> list[FontFile]:
        resolved: list[FontFile] = []
        seen: set[tuple[str, int]] = set()
        for ref in stack.fonts:
            face = self.resolve(ref)
            if face is None or face.key in seen:
                continue
            seen.add(face.key)
            resolved.append(face)
        return resolved

    def load(self, face: FontFile, size: int) -> ImageFont.FreeTypeFont:
        key = (str(face.path), face.index, size)
        if key not in self._pil_fonts:
            self._pil_fonts[key] = ImageFont.truetype(
                str(face.path), size=size, index=face.index
            )
        return self._pil_fonts[key]

    def glyph_supported(self, face: FontFile, char: str) -> bool:
        if char == " ":
            return True
        return ord(char) in _codepoints(str(face.path), face.index)

    def text_width(self, face: FontFile, size: int, text: str, tracking: float = 0.0) -> float:
        """Advance width including per-glyph letter-spacing (tracking)."""
        if not text:
            return 0.0
        font = self.load(face, size)
        total = 0.0
        for index, char in enumerate(text):
            total += font.getlength(char)
            if index < len(text) - 1:
                total += tracking
        return total

    def metrics(self, face: FontFile, size: int) -> tuple[int, int]:
        """(ascent, descent) in pixels at the given size."""
        return self.load(face, size).getmetrics()


_DEFAULT_MANAGER: FontManager | None = None


def default_font_manager() -> FontManager:
    """A process-wide shared FontManager (lazy singleton)."""
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = FontManager()
    return _DEFAULT_MANAGER
