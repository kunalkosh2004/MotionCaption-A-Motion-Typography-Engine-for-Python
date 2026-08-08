import pytest

from motion_caption import Color, EmphasisMode, Point, PropertyKind, Region, TextAlign
from motion_caption.ir import (
    AnimationTrack,
    KeyframeTrack,
    PlacementRegion,
    StyleTrack,
    SubtitleEvent,
    SubtitleTimeline,
    Track,
    WordEvent,
)
from motion_caption.ir.typography import ResolvedFont, ResolvedTypography
from motion_caption.models.geometry import Box
from motion_caption.models.keyframe import Keyframe, KeyframeTimeline

FONT = ResolvedFont(family="Helvetica", weight=400, path="/fonts/helvetica.ttf")
STYLE = ResolvedTypography(font=FONT, font_size=48.0, fill="#FFFFFF")


def _opacity_track(start=0.0, end=2.0):
    return KeyframeTimeline(
        kind=PropertyKind.OPACITY,
        keyframes=[
            Keyframe(start, 0.0, ease="ease-in-out"),
            Keyframe(end, 1.0),
        ],
    )


def _word(text="Hello", left=0.0, top=0.0) -> WordEvent:
    return WordEvent(
        text=text,
        start=0.0,
        end=2.0,
        box=Box.from_xywh(left, top, 100.0, 40.0),
    )


class TestAnimationTrack:
    def test_add_and_sample_merges_tracks(self):
        track = AnimationTrack().add(_opacity_track())
        track.add(
            KeyframeTimeline(
                kind=PropertyKind.POSITION,
                keyframes=[
                    Keyframe(0.0, Point(0, 0)),
                    Keyframe(2.0, Point(50, 0)),
                ],
            )
        )
        region = track.sample(1.0)
        assert isinstance(region, Region)
        assert region.position == Point(x=25.0, y=0.0)
        assert region.scale == Point(1, 1)
        assert 0.0 < region.opacity < 1.0

    def test_empty_track_is_static(self):
        assert AnimationTrack().is_static()

    def test_sample_outside_range_holds(self):
        track = AnimationTrack().add(_opacity_track())
        assert track.sample(-5.0).opacity == pytest.approx(0.0)
        assert track.sample(99.0).opacity == pytest.approx(1.0)

    def test_phases_are_metadata(self):
        track = AnimationTrack().add(_opacity_track())
        track.phases["in"] = (0.0, 0.4)
        assert track.phases["in"] == (0.0, 0.4)

    def test_start_end_from_tracks(self):
        track = AnimationTrack().add(_opacity_track(0.5, 1.5))
        assert track.start == pytest.approx(0.5)
        assert track.end == pytest.approx(1.5)


class TestWordEvent:
    def test_missing_animation_is_static(self):
        word = _word()
        assert word.region_at(123.0) == Region()

    def test_animation_sampled(self):
        word = _word()
        word.animation = AnimationTrack().add(_opacity_track())
        assert word.region_at(99.0).opacity == pytest.approx(1.0)

    def test_emphasis_and_importance_carried(self):
        word = WordEvent(
            text="HEY",
            start=0.0,
            end=1.0,
            importance=0.8,
            emphasis=EmphasisMode.HIGH,
            box=Box(0, 0, 10, 10),
        )
        assert word.importance == 0.8
        assert word.emphasis is EmphasisMode.HIGH


class TestSubtitleEvent:
    def test_sample_returns_per_word_regions(self):
        event = SubtitleEvent(
            start=0.0,
            end=2.0,
            text="Hello world",
            region=PlacementRegion(box=Box(0, 0, 200, 40)),
            words=[_word(), _word(text="world")],
        )
        regions = event.sample(0.0)
        assert len(regions) == 2
        assert all(isinstance(r, Region) for r in regions)

    def test_duration(self):
        event = SubtitleEvent(start=1.0, end=3.0, text="x")
        assert event.duration == 2.0


class TestSubtitleTimeline:
    def _timeline(self) -> SubtitleTimeline:
        style = StyleTrack(name="base", typography=STYLE)
        event = SubtitleEvent(
            start=0.0,
            end=2.0,
            text="Hello",
            style=style,
            region=PlacementRegion(box=Box(0, 0, 100, 40)),
            words=[_word()],
        )
        return SubtitleTimeline(
            metadata={"title": "demo"},
            styles=[style],
            tracks=[Track(name="main", speaker="s1", events=[event])],
        )

    def test_events_flattened(self):
        timeline = self._timeline()
        assert len(timeline.events) == 1
        assert len(timeline.words) == 1

    def test_events_at(self):
        timeline = self._timeline()
        assert len(timeline.events_at(1.0)) == 1
        assert timeline.events_at(2.5) == []
        assert timeline.events_at(2.0) == []

    def test_duration(self):
        assert self._timeline().duration == pytest.approx(2.0)

    def test_style_lookup(self):
        timeline = self._timeline()
        assert timeline.style("base") is not None
        assert timeline.style("nope") is None

    def test_json_roundtrip_is_stable(self):
        timeline = self._timeline()
        dumped = timeline.model_dump_json()
        assert SubtitleTimeline.model_validate_json(dumped) == timeline

    def test_identical_inputs_produce_identical_bytes(self):
        a = self._timeline().model_dump_json()
        b = self._timeline().model_dump_json()
        assert a == b

    def test_align_kept_in_typography(self):
        assert STYLE.align is TextAlign.CENTER
        assert STYLE.fill == Color("#FFFFFF")


class TestKeyframeTrack:
    def test_kind_carried(self):
        track = KeyframeTrack(kind=PropertyKind.OPACITY, timeline=_opacity_track())
        assert track.kind is PropertyKind.OPACITY
        assert track.timeline.sample(1.0) > 0.0
