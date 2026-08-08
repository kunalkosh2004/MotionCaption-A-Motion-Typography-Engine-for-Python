"""The canonical intermediate representation: ``SubtitleTimeline``.

The IR is pure data over ``models/`` primitives — it imports no theme, font,
layout or placement code. Everything a renderer or exporter needs to draw a
caption is here: resolved typography, measured word boxes, keyframed motion
and final placement regions.

Coordinates are design-space pixels for ``timeline.resolution`` (default
1920x1080). ``timeline.scale`` maps design px to output px for the requested
canvas; exporters apply it once at emit time. The IR itself is never mutated
to fit a target — that is the job of backends.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from motion_caption.ir.typography import ResolvedTypography
from motion_caption.models.geometry import Box, Point
from motion_caption.models.keyframe import KeyframeTimeline, PropertyKind, Region
from motion_caption.models.transcript import EmphasisMode
from motion_caption.models.units import DesignSpace, Resolution


class KeyframeTrack(BaseModel):
    """One animatable property as an ordered keyframe timeline."""

    kind: PropertyKind
    timeline: KeyframeTimeline


class AnimationTrack(BaseModel):
    """The motion of one element: per-property keyframe tracks that sample to
    a ``Region``, plus optional named phase spans (``"in"``/``"out"``/``"idle"``).

    ``sample`` is deterministic and identical to ``RegionTimeline`` semantics:
    values hold before the first and after the last keyframe.
    """

    tracks: dict[PropertyKind, KeyframeTrack] = Field(default_factory=dict)
    phases: dict[str, tuple[float, float]] = Field(default_factory=dict)

    def add(self, timeline: KeyframeTimeline) -> AnimationTrack:
        self.tracks[timeline.kind] = KeyframeTrack(kind=timeline.kind, timeline=timeline)
        return self

    @property
    def start(self) -> float:
        return min((t.timeline.start for t in self.tracks.values()), default=0.0)

    @property
    def end(self) -> float:
        return max((t.timeline.end for t in self.tracks.values()), default=0.0)

    def sample(self, t: float) -> Region:
        data: dict[str, Any] = {}
        for track in self.tracks.values():
            data[track.kind.value] = track.timeline.sample(t)
        return Region(**data)

    def is_static(self) -> bool:
        return not self.tracks


class StyleTrack(BaseModel):
    """A named block-level typography treatment.

    Events embed the value directly so exporters never dereference ids; the
    timeline keeps an interned list for deduplication on serialization.
    """

    name: str
    typography: ResolvedTypography


class PlacementRegion(BaseModel):
    """Where a caption element sits on the canvas (design-space px)."""

    box: Box = Field(default_factory=Box)
    anchor: Point = Field(default_factory=lambda: Point(0.0, 0.0))
    speaker: str | None = None
    layer: int = 0

    @property
    def width(self) -> float:
        return self.box.width

    @property
    def height(self) -> float:
        return self.box.height


class WordEvent(BaseModel):
    """One word inside a ``SubtitleEvent``, with its own motion and style."""

    text: str = Field(min_length=1)
    start: float = Field(default=0.0, ge=0.0)
    end: float = Field(default=0.0, ge=0.0)
    importance: float = Field(default=0.0, ge=0.0, le=1.0)
    emphasis: EmphasisMode = EmphasisMode.NONE
    box: Box
    typography: ResolvedTypography | None = None
    animation: AnimationTrack | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def region_at(self, t: float) -> Region:
        """Sample this word's motion; a missing animation means fully static."""
        if self.animation is None or self.animation.is_static():
            return Region()
        return self.animation.sample(t)


class SubtitleEvent(BaseModel):
    """One caption: a group of words on screen together over ``[start, end]``."""

    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    text: str = Field(min_length=1)
    style: StyleTrack | None = None
    region: PlacementRegion = Field(default_factory=PlacementRegion)
    words: list[WordEvent] = Field(default_factory=list)
    speaker: str | None = None
    layer: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def sample(self, t: float) -> list[Region]:
        return [word.region_at(t) for word in self.words]


class Track(BaseModel):
    """A timeline lane: one speaker or layer's ordered events."""

    name: str
    speaker: str | None = None
    events: list[SubtitleEvent] = Field(default_factory=list)


class SubtitleTimeline(BaseModel):
    """The canonical IR — the single source of truth for every backend.

    ``format_version`` guards serialization compat. ``scale`` maps design px
    to the requested output canvas (``= design.policy.scale(resolution,
    design.reference)``); backends multiply geometry by it.
    """

    format_version: str = "1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)
    resolution: Resolution = Field(default_factory=lambda: Resolution(width=1920, height=1080))
    design: DesignSpace = Field(default_factory=DesignSpace)
    scale: float = 1.0
    styles: list[StyleTrack] = Field(default_factory=list)
    tracks: list[Track] = Field(default_factory=list)

    @property
    def events(self) -> list[SubtitleEvent]:
        return [event for track in self.tracks for event in track.events]

    @property
    def words(self) -> list[WordEvent]:
        return [word for event in self.events for word in event.words]

    @property
    def start(self) -> float:
        events = self.events
        return min((e.start for e in events), default=0.0)

    @property
    def end(self) -> float:
        events = self.events
        return max((e.end for e in events), default=0.0)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def events_at(self, t: float) -> list[SubtitleEvent]:
        """Events overlapping time ``t`` (inclusive start, exclusive end)."""
        return [e for e in self.events if e.start <= t < e.end]

    def words_at(self, t: float) -> list[WordEvent]:
        return [w for event in self.events_at(t) for w in event.words]

    def style(self, name: str) -> StyleTrack | None:
        for entry in self.styles:
            if entry.name == name:
                return entry
        return None
