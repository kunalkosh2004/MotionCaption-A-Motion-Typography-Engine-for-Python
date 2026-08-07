"""Output canvas: standard resolutions and aspect-ratio helpers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from motion_caption.models.units import Resolution


class AspectRatio(StrEnum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"


class StandardResolution(StrEnum):
    """Named output resolutions used across platforms."""

    HD_720P = "720p"
    HD_1080P = "1080p"
    QHD_2K = "2k"
    UHD_4K = "4k"
    PORTRAIT = "portrait"  # 1080x1920
    SHORTS = "shorts"  # 1080x1920
    SQUARE = "square"  # 1080x1080

    def resolution(self) -> Resolution:
        return _STANDARD_RESOLUTIONS[self]


_STANDARD_RESOLUTIONS: dict[StandardResolution, Resolution] = {
    StandardResolution.HD_720P: Resolution(width=1280, height=720),
    StandardResolution.HD_1080P: Resolution(width=1920, height=1080),
    StandardResolution.QHD_2K: Resolution(width=2560, height=1440),
    StandardResolution.UHD_4K: Resolution(width=3840, height=2160),
    StandardResolution.PORTRAIT: Resolution(width=1080, height=1920),
    StandardResolution.SHORTS: Resolution(width=1080, height=1920),
    StandardResolution.SQUARE: Resolution(width=1080, height=1080),
}


class Canvas(BaseModel):
    """The output frame a caption is composed for."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @classmethod
    def from_standard(cls, resolution: StandardResolution | str) -> Canvas:
        res = StandardResolution(resolution).resolution()
        return cls(width=res.width, height=res.height)

    @property
    def resolution(self) -> Resolution:
        return Resolution(width=self.width, height=self.height)

    @property
    def aspect_ratio(self) -> AspectRatio:
        if self.width == self.height:
            return AspectRatio.SQUARE
        return AspectRatio.PORTRAIT if self.height > self.width else AspectRatio.LANDSCAPE

    @property
    def is_portrait(self) -> bool:
        return self.aspect_ratio is AspectRatio.PORTRAIT

    @property
    def is_landscape(self) -> bool:
        return self.aspect_ratio is AspectRatio.LANDSCAPE

    @property
    def is_square(self) -> bool:
        return self.aspect_ratio is AspectRatio.SQUARE
