"""The unified compiler input: ``CaptionRequest``.

Every public API accepts (or internally builds) a ``CaptionRequest``. It is
pure data and serializable, so requests round-trip through JSON — the compiler
is deterministic over the request, and AI/editor tooling can produce one
without importing core.

AI output arrives *already computed* as ``llm_annotations`` (an
``AIContribution``). Providers are never imported by core.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

from motion_caption.animations.engine import AnimationConfig
from motion_caption.canvas import StandardResolution
from motion_caption.layout.engine import LayoutOptions
from motion_caption.models.transcript import EmphasisMode, Transcript
from motion_caption.models.units import DesignSpace, Resolution
from motion_caption.placement.engine import PlacementConfig
from motion_caption.placement.faces import Face
from motion_caption.placement.safe_areas import SafeArea
from motion_caption.reading.engine import DEFAULT_TARGET_WPS
from motion_caption.segmentation.rules import SegmentationConfig
from motion_caption.themes.spec import ThemeSpec

_RESOLUTION_PATTERN = re.compile(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$")


class SpeakerTrack(BaseModel):
    """Words attributed to one speaker, plus a vertical placement bias."""

    id: str = Field(min_length=1)
    word_indices: list[int] = Field(default_factory=list)
    bias: float = Field(default=0.0, ge=-1.0, le=1.0)


class AIContribution(BaseModel):
    """The complete, deterministic input an AI provider may contribute.

    All fields are optional; the compiler falls back to rule-based behavior
    for anything absent. Indices address ``transcript.words``.
    """

    importance: dict[int, float] | None = None
    emphasis: dict[int, EmphasisMode] | None = None
    splits: list[list[int]] | None = None
    theme: str | None = None
    emotion: str | None = None


class CompileOptions(BaseModel):
    """Knobs for each pure stage of the compiler."""

    strategy: str = "sentence"
    segmentation: SegmentationConfig | None = None
    reading: bool = True
    target_wps: float = DEFAULT_TARGET_WPS
    animation: AnimationConfig | None = None
    layout: LayoutOptions | None = None
    placement: PlacementConfig | None = None
    karaoke: bool = False


class CaptionRequest(BaseModel):
    """Everything the compiler needs to produce a ``SubtitleTimeline``.

    ``theme`` may be a ``ThemeSpec`` or a registry name; resolution happens in
    the compiler so the request is serializable. ``resolution`` accepts a
    ``Resolution``, a ``StandardResolution`` name (``"1080p"``), or a
    ``"WxH"`` string.
    """

    metadata: dict[str, Any] = Field(default_factory=dict)
    transcript: Transcript
    faces: list[Face] = Field(default_factory=list)
    safe_area: SafeArea | None = None
    platform: str | None = None
    theme: str | ThemeSpec | None = None
    llm_annotations: AIContribution | None = None
    speaker_tracks: list[SpeakerTrack] = Field(default_factory=list)
    resolution: Resolution | StandardResolution | str | None = None
    design: DesignSpace | None = None
    options: CompileOptions | None = None
    future_extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _parse_resolution(self) -> CaptionRequest:
        value = self.resolution
        if value is None or isinstance(value, (Resolution, StandardResolution)):
            return self
        if isinstance(value, str):
            if value in StandardResolution._value2member_map_:
                return self
            match = _RESOLUTION_PATTERN.match(value)
            if match is None:
                raise ValueError(
                    f"invalid resolution string: {value!r}; use 'WxH' or a StandardResolution name"
                )
            self.resolution = Resolution(
                width=int(match.group(1)), height=int(match.group(2))
            )
        return self

    @property
    def resolved_resolution(self) -> Resolution:
        value = self.resolution
        if value is None:
            return Resolution(width=1920, height=1080)
        if isinstance(value, Resolution):
            return value
        return StandardResolution(value).resolution()

    @property
    def resolved_design(self) -> DesignSpace:
        if self.design is not None:
            return self.design
        return DesignSpace(reference=self.resolved_resolution)

    @property
    def resolved_options(self) -> CompileOptions:
        return self.options or CompileOptions()
