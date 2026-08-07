import pytest

from motion_caption import (
    Color,
    Keyframe,
    KeyframeTimeline,
    Point,
    PropertyKind,
    Region,
    RegionTimeline,
)


def _opacity_timeline():
    return KeyframeTimeline(
        kind=PropertyKind.OPACITY,
        keyframes=[
            Keyframe(time=0.0, value=0.0, ease="ease-in-out"),
            Keyframe(time=1.0, value=1.0),
        ],
    )


class TestKeyframeTimeline:
    def test_scalar_sample(self):
        timeline = _opacity_timeline()
        assert timeline.sample(0.0) == pytest.approx(0.0)
        assert timeline.sample(0.5) == pytest.approx(0.5, abs=1e-3)
        assert timeline.sample(1.0) == pytest.approx(1.0)

    def test_holds_outside_range(self):
        timeline = _opacity_timeline()
        assert timeline.sample(-5.0) == pytest.approx(0.0)
        assert timeline.sample(99.0) == pytest.approx(1.0)

    def test_sorts_keyframes(self):
        timeline = KeyframeTimeline(
            kind=PropertyKind.OPACITY,
            keyframes=[
                Keyframe(time=1.0, value=1.0),
                Keyframe(time=0.0, value=0.0),
            ],
        )
        assert [k.time for k in timeline.keyframes] == [0.0, 1.0]

    def test_point_interpolation(self):
        timeline = KeyframeTimeline(
            kind=PropertyKind.POSITION,
            keyframes=[
                Keyframe(time=0.0, value=Point(0, 0)),
                Keyframe(time=1.0, value=Point(100, 50)),
            ],
        )
        assert timeline.sample(0.5) == Point(x=50.0, y=25.0)

    def test_scalar_to_uniform_point(self):
        timeline = KeyframeTimeline(
            kind=PropertyKind.SCALE,
            keyframes=[
                Keyframe(time=0.0, value=0.5),
                Keyframe(time=1.0, value=1.0),
            ],
        )
        assert timeline.sample(0.5) == Point(x=0.75, y=0.75)

    def test_color_interpolation(self):
        timeline = KeyframeTimeline(
            kind=PropertyKind.COLOR,
            keyframes=[
                Keyframe(time=0.0, value="#000000"),
                Keyframe(time=1.0, value="#ffffff"),
            ],
        )
        assert timeline.sample(0.5) == Color("#808080")

    def test_wrong_value_type_raises(self):
        with pytest.raises(ValueError):
            KeyframeTimeline(
                kind=PropertyKind.OPACITY,
                keyframes=[Keyframe(time=0.0, value=Point(1, 2))],
            )

    def test_start_end_properties(self):
        timeline = _opacity_timeline()
        assert timeline.start == 0.0
        assert timeline.end == 1.0

    def test_value_type(self):
        assert _opacity_timeline().value_type == "scalar"
        assert KeyframeTimeline(
            kind=PropertyKind.POSITION, keyframes=[Keyframe(time=0, value=Point(0, 0))]
        ).value_type == "point"
        assert KeyframeTimeline(
            kind=PropertyKind.COLOR, keyframes=[Keyframe(time=0, value="#000000")]
        ).value_type == "color"

    def test_eased_transition_uses_source_ease(self):
        linear = KeyframeTimeline(
            kind=PropertyKind.OPACITY,
            keyframes=[
                Keyframe(time=0.0, value=0.0, ease="ease-in-out"),
                Keyframe(time=1.0, value=1.0),
            ],
        )
        assert linear.sample(0.5) == pytest.approx(0.5, abs=1e-3)

    def test_spring_ease_track(self):
        timeline = KeyframeTimeline(
            kind=PropertyKind.OPACITY,
            keyframes=[
                Keyframe(time=0.0, value=0.0, ease="spring"),
                Keyframe(time=1.0, value=1.0),
            ],
        )
        assert timeline.sample(0.5) > 0.5

    def test_positional_construction(self):
        timeline = KeyframeTimeline(
            kind=PropertyKind.OPACITY,
            keyframes=[Keyframe(0.0, 0.0, ease="ease-in-out"), Keyframe(1.0, 1.0)],
        )
        assert timeline.sample(0.5) == pytest.approx(0.5, abs=1e-3)


class TestRegion:
    def test_defaults(self):
        region = Region()
        assert region.position == Point(0, 0)
        assert region.scale == Point(1, 1)
        assert region.opacity == 1.0
        assert region.rotation == 0.0
        assert region.color is None

    def test_custom(self):
        region = Region(position=Point(10, 20), opacity=0.5, color="#ff0000")
        assert region.position.x == 10
        assert region.opacity == 0.5
        assert region.color == Color("#ff0000")


class TestRegionTimeline:
    def test_sample_merges_tracks_and_defaults(self):
        timeline = RegionTimeline()
        timeline.add_track(_opacity_timeline())
        timeline.add_track(
            KeyframeTimeline(
                kind=PropertyKind.POSITION,
                keyframes=[
                    Keyframe(time=0, value=Point(10, 20)),
                    Keyframe(time=1, value=Point(30, 40)),
                ],
            )
        )
        region = timeline.sample(0.5)
        assert region.opacity == pytest.approx(0.5, abs=1e-3)
        assert region.position == Point(x=20.0, y=30.0)
        assert region.scale == Point(1, 1)
        assert region.rotation == 0.0

    def test_empty_timeline_gives_defaults(self):
        region = RegionTimeline().sample(0.0)
        assert region == Region()

    def test_add_track_returns_self(self):
        timeline = RegionTimeline()
        assert timeline.add_track(_opacity_timeline()) is timeline
