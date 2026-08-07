import pytest

from motion_caption import Box, Canvas
from motion_caption.layout import PlacedBlock
from motion_caption.placement import (
    PLACEMENT_REGISTRY,
    PLATFORM_SAFE_AREAS,
    Face,
    PlacementConfig,
    SafeArea,
    avoid_faces,
    place,
    platform_safe_area,
)
from motion_caption.typography.measure import MeasuredBlock

CANVAS = Canvas(width=1080, height=1920)


def _block(width: float, height: float) -> PlacedBlock:
    return PlacedBlock(
        block=MeasuredBlock(lines=[], width=width, height=height),
        box=Box.from_xywh(0, 0, width, height),
    )


class TestSafeAreas:
    def test_resolve(self):
        safe = SafeArea(top=0.1, bottom=0.2, left=0.05, right=0.15)
        box = safe.resolve(Canvas(width=1000, height=2000))
        assert box == Box(left=50, top=200, right=850, bottom=1600)

    def test_platforms_known(self):
        for name in ("tiktok", "instagram_reels", "youtube_shorts", "landscape", "square", "none"):
            assert name in PLATFORM_SAFE_AREAS

    def test_alias(self):
        assert platform_safe_area("shorts") is platform_safe_area("youtube_shorts")
        assert platform_safe_area("reels") is platform_safe_area("instagram_reels")

    def test_unknown_platform_raises(self):
        with pytest.raises(KeyError):
            platform_safe_area("twitch")

    def test_insets_in_range(self):
        for safe in PLATFORM_SAFE_AREAS.values():
            assert 0.0 <= safe.top <= 1.0
            assert 0.0 <= safe.bottom <= 1.0
            assert 0.0 <= safe.left <= 1.0
            assert 0.0 <= safe.right <= 1.0


class TestPlaceStrategies:
    def test_bottom_stays_in_safe_region(self):
        block = _block(200, 100)
        final = place(block, CANVAS, config=PlacementConfig(platform="tiktok"))
        safe = platform_safe_area("tiktok").resolve(CANVAS)
        assert final.box.left >= safe.left
        assert final.box.top >= safe.top
        assert final.box.right <= safe.right
        assert final.box.bottom == pytest.approx(safe.bottom)

    def test_top_aligned_to_safe_top(self):
        block = _block(200, 100)
        final = place(block, CANVAS, config=PlacementConfig(strategy="top", platform="square"))
        safe = platform_safe_area("square").resolve(CANVAS)
        assert final.box.top == pytest.approx(safe.top)

    def test_center(self):
        block = _block(200, 100)
        final = place(block, CANVAS, config=PlacementConfig(strategy="center", platform="none"))
        assert final.box.center_x == pytest.approx(1080 / 2)
        assert final.box.center_y == pytest.approx(1920 / 2)

    def test_default_uses_full_canvas(self):
        block = _block(200, 100)
        final = place(block, CANVAS)
        assert final.box.bottom == pytest.approx(1920)
        assert final.box.left == pytest.approx((1080 - 200) / 2)

    def test_preserves_size(self):
        block = _block(200, 100)
        for name in ("bottom", "top", "center", "face-aware"):
            final = place(block, CANVAS, config=PlacementConfig(strategy=name))
            assert final.box.width == pytest.approx(200)
            assert final.box.height == pytest.approx(100)

    def test_unknown_strategy_raises(self):
        with pytest.raises(KeyError, match="no placement strategy registered"):
            place(_block(200, 100), CANVAS, config=PlacementConfig(strategy="nope"))

    def test_plugin_strategy(self):
        def pinned(canvas, config, box, faces):
            return Box.from_xywh(10, 10, box.width, box.height)

        PLACEMENT_REGISTRY.add("pinned", pinned)
        final = place(_block(200, 100), CANVAS, config=PlacementConfig(strategy="pinned"))
        assert final.box.left == pytest.approx(10)
        assert final.box.top == pytest.approx(10)


class TestFaceAware:
    def test_avoids_overlapping_face(self):
        block = _block(200, 100)
        face = Face(box=Box.from_xywh(400, 1700, 700, 1900))
        final = place(
            block, CANVAS, config=PlacementConfig(strategy="face-aware"), faces=[face]
        )
        overlap = not (
            final.box.right <= face.box.left
            or face.box.right <= final.box.left
            or final.box.bottom <= face.box.top
            or face.box.bottom <= final.box.top
        )
        assert not overlap

    def test_unchanged_when_clear(self):
        block = _block(200, 100)
        face = Face(box=Box.from_xywh(100, 100, 300, 300))
        plain = place(block, CANVAS, config=PlacementConfig(strategy="bottom"))
        aware = place(
            block, CANVAS, config=PlacementConfig(strategy="face-aware"), faces=[face]
        )
        assert aware.box == plain.box

    def test_margin_keeps_gap(self):
        block = _block(200, 100)
        face = Face(box=Box.from_xywh(0, 1820, 1080, 1920))
        final = place(
            block,
            CANVAS,
            config=PlacementConfig(strategy="face-aware", face_margin=10),
            faces=[face],
        )
        assert final.box.bottom <= face.box.top - 10


class TestAvoidFaces:
    def test_moves_above_face(self):
        region = Box.from_xywh(400, 500, 300, 50)
        face = Face(box=Box.from_xywh(400, 400, 700, 600))
        canvas = Box(0, 0, 1000, 1000)
        result = avoid_faces(region, [face], canvas)
        interior_overlap = (
            result.right > face.box.left
            and face.box.right > result.left
            and result.bottom > face.box.top
            and face.box.bottom > result.top
        )
        assert not interior_overlap
        assert result.top >= 0 and result.bottom <= 1000

    def test_no_face_returns_unchanged(self):
        region = Box.from_xywh(400, 500, 300, 50)
        canvas = Box(0, 0, 1000, 1000)
        assert avoid_faces(region, [], canvas) == region

    def test_clear_region_unchanged(self):
        region = Box.from_xywh(100, 800, 300, 50)
        face = Face(box=Box.from_xywh(400, 400, 700, 600))
        canvas = Box(0, 0, 1000, 1000)
        assert avoid_faces(region, [face], canvas) == region
