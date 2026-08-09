"""Platform presets: one object per target platform.

A preset bundles everything a target platform implies — output resolution,
safe areas (reused from the core ``PLATFORM_SAFE_AREAS`` catalog), default
frame rate and caption placement bias — so callers and the CLI can say
``preset=\"youtube_shorts\"`` instead of configuring five knobs. Presets never
hardcode behavior *inside* the compiler; they only fill ordinary
``CaptionRequest`` fields (``platform``, ``resolution``, ``safe_area``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from motion_caption.placement import SafeArea, platform_safe_area


@dataclass(frozen=True, slots=True)
class PlatformPreset:
    """A named bundle of target-platform defaults."""

    name: str
    resolution: tuple[int, int]
    safe_area: SafeArea
    fps: int = 30
    placement_bias: float = 0.0

    def request_fields(self) -> dict[str, Any]:
        """The ``CaptionRequest`` fields this preset contributes."""
        return {
            "platform": self.name,
            "resolution": f"{self.resolution[0]}x{self.resolution[1]}",
            "safe_area": self.safe_area,
        }

    # -- built-ins -----------------------------------------------------------

    @classmethod
    def youtube_shorts(cls) -> PlatformPreset:
        return cls(
            "youtube_shorts",
            (1080, 1920),
            platform_safe_area("youtube_shorts"),
            fps=30,
        )

    @classmethod
    def tiktok(cls) -> PlatformPreset:
        return cls("tiktok", (1080, 1920), platform_safe_area("tiktok"), fps=30)

    @classmethod
    def instagram_reels(cls) -> PlatformPreset:
        return cls(
            "instagram_reels",
            (1080, 1920),
            platform_safe_area("instagram_reels"),
            fps=30,
        )

    @classmethod
    def youtube_landscape(cls) -> PlatformPreset:
        return cls("youtube_landscape", (1920, 1080), platform_safe_area("landscape"), fps=30)

    @classmethod
    def square(cls) -> PlatformPreset:
        return cls("square", (1080, 1080), platform_safe_area("square"), fps=30)


_PRESETS: dict[str, PlatformPreset] = {
    preset.name: preset
    for preset in (
        PlatformPreset.youtube_shorts(),
        PlatformPreset.tiktok(),
        PlatformPreset.instagram_reels(),
        PlatformPreset.youtube_landscape(),
        PlatformPreset.square(),
    )
}

_ALIASES: dict[str, str] = {
    "shorts": "youtube_shorts",
    "yt_shorts": "youtube_shorts",
    "reels": "instagram_reels",
    "ig": "instagram_reels",
    "ig_reels": "instagram_reels",
    "landscape": "youtube_landscape",
    "square": "square",
}

PLATFORM_PRESETS: dict[str, PlatformPreset] = dict(_PRESETS)


def platform_preset(name: str) -> PlatformPreset:
    """Look up a preset by name (aliases accepted); unknown names raise ``KeyError``."""
    key = _ALIASES.get(name, name)
    try:
        return _PRESETS[key]
    except KeyError:
        available = ", ".join(sorted(_PRESETS))
        raise KeyError(
            f"unknown platform preset {name!r}; available: {available}"
        ) from None


def available_presets() -> list[str]:
    """Sorted names of every built-in preset (aliases excluded)."""
    return sorted(_PRESETS)
