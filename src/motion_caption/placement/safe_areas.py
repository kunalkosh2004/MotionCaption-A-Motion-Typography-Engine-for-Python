"""Safe areas: platform UI insets kept clear by placement.

Insets are fractional (0..1) fractions of the canvas so they stay valid at
any output resolution. The catalog covers the major short-form and
traditional platforms; unknown names raise ``KeyError``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from motion_caption.canvas import Canvas
from motion_caption.models.geometry import Box


class SafeArea(BaseModel):
    """Fractional insets (0..1 of the canvas) to keep free of platform UI."""

    top: float = Field(default=0.0, ge=0.0, le=1.0)
    bottom: float = Field(default=0.0, ge=0.0, le=1.0)
    left: float = Field(default=0.0, ge=0.0, le=1.0)
    right: float = Field(default=0.0, ge=0.0, le=1.0)

    def resolve(self, canvas: Canvas) -> Box:
        """Resolve the fractional insets to a pixel box on the canvas."""
        return Box(
            left=canvas.width * self.left,
            top=canvas.height * self.top,
            right=canvas.width * (1.0 - self.right),
            bottom=canvas.height * (1.0 - self.bottom),
        )


PLATFORM_SAFE_AREAS: dict[str, SafeArea] = {
    "tiktok": SafeArea(top=0.06, bottom=0.08, left=0.03, right=0.18),
    "instagram_reels": SafeArea(top=0.08, bottom=0.10, left=0.02, right=0.16),
    "youtube_shorts": SafeArea(top=0.10, bottom=0.06, left=0.04, right=0.20),
    "landscape": SafeArea(top=0.06, bottom=0.12, left=0.02, right=0.04),
    "square": SafeArea(top=0.06, bottom=0.10, left=0.04, right=0.04),
    "none": SafeArea(top=0.0, bottom=0.0, left=0.0, right=0.0),
}

_PLATFORM_ALIASES: dict[str, str] = {
    "ig": "instagram_reels",
    "reels": "instagram_reels",
    "ig_reels": "instagram_reels",
    "shorts": "youtube_shorts",
    "yt_shorts": "youtube_shorts",
}


def platform_safe_area(name: str) -> SafeArea:
    """Look up a named platform safe area (aliases accepted)."""
    key = _PLATFORM_ALIASES.get(name, name)
    return PLATFORM_SAFE_AREAS[key]
