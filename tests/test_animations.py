import pytest

from motion_caption import (
    AnimationPersonality,
    EasingKind,
    EmphasisMode,
    Segment,
    ThemeSpec,
    Word,
    resolve_theme,
)
from motion_caption.animations import (
    ANIMATION_REGISTRY,
    AnimationConfig,
    animate_segment,
    build_word_items,
)
from motion_caption.models.keyframe import PropertyKind

STRATEGIES = {
    "none",
    "fade",
    "slide",
    "pop",
    "scale",
    "bounce",
    "spring",
    "elastic",
    "overshoot",
    "ripple",
    "rotate",
    "blur",
    "glow",
    "karaoke",
    "pulse",
}


@pytest.fixture(scope="module")
def theme():
    return resolve_theme(ThemeSpec(name="anim-test"))


@pytest.fixture
def segment() -> Segment:
    return Segment(
        text="hello world",
        start=0.0,
        end=2.0,
        words=[
            Word(text="hello", start=0.1, end=0.6, importance=0.8, emphasis=EmphasisMode.HIGH),
            Word(text="world", start=0.7, end=1.2),
        ],
    )


class TestRegistry:
    def test_expected_strategies_registered(self):
        assert set(ANIMATION_REGISTRY.keys) >= STRATEGIES

    def test_static_alias(self):
        assert ANIMATION_REGISTRY.get("static") is ANIMATION_REGISTRY.get("none")

    def test_unknown_strategy_raises(self, theme, segment):
        with pytest.raises(KeyError, match="no animation registered"):
            build_word_items([segment], theme, AnimationConfig(strategy="nope"))

    def test_plugin_template(self, theme, segment):
        def always_pop(ctx):
            from motion_caption.models.keyframe import RegionTimeline

            return RegionTimeline().add_track(
                ANIMATION_REGISTRY.get("pop")(ctx).tracks[PropertyKind.SCALE]
            )

        ANIMATION_REGISTRY.add("always-pop", always_pop)
        items = build_word_items([segment], theme, AnimationConfig(strategy="always-pop"))
        assert items[0].region.sample(0.0).scale.x < 1.0


class TestTiming:
    def test_fade_uses_segment_timing(self, theme, segment):
        item = build_word_items([segment], theme)[0]
        opacity = item.region.tracks[PropertyKind.OPACITY]
        assert opacity.start == pytest.approx(segment.start)
        assert opacity.end == pytest.approx(segment.end)
        assert item.region.sample(0.0).opacity == pytest.approx(0.0)
        assert item.region.sample(1.0).opacity == pytest.approx(1.0)
        assert item.region.sample(2.0).opacity == pytest.approx(0.0)

    def test_fade_holds_outside_range(self, theme, segment):
        item = build_word_items([segment], theme)[0]
        assert item.region.sample(-1.0).opacity == pytest.approx(0.0)
        assert item.region.sample(3.0).opacity == pytest.approx(0.0)

    def test_karaoke_uses_word_timing(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="karaoke"))[0]
        opacity = item.region.tracks[PropertyKind.OPACITY]
        assert opacity.start == pytest.approx(segment.words[0].start)
        assert opacity.end == pytest.approx(segment.words[0].end)

    def test_custom_windows(self, theme, segment):
        config = AnimationConfig(strategy="fade", in_window=0.5, out_window=0.5)
        item = build_word_items([segment], theme, config)[0]
        assert item.region.sample(1.0).opacity == pytest.approx(1.0)
        assert item.region.sample(1.6).opacity < 1.0
        assert item.region.sample(2.0).opacity == pytest.approx(0.0)


class TestTemplates:
    def test_none_is_static(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="none"))[0]
        for t in (0.0, 0.5, 1.0, 1.5, 2.0):
            assert item.region.sample(t).opacity == pytest.approx(1.0)

    def test_pop_scales_in(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="pop"))[0]
        assert item.region.sample(0.0).scale.x == pytest.approx(0.6)
        assert item.region.sample(1.0).scale.x == pytest.approx(1.0)

    def test_scale_param(self, theme, segment):
        config = AnimationConfig(strategy="pop", params={"start_scale": 0.3})
        item = build_word_items([segment], theme, config)[0]
        assert item.region.sample(0.0).scale.x == pytest.approx(0.3)

    def test_slide_moves_and_returns(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="slide"))[0]
        assert item.region.sample(0.0).position.y == pytest.approx(60.0)
        assert item.region.sample(1.0).position.y == pytest.approx(0.0)
        assert item.region.sample(2.0).position.y == pytest.approx(60.0)

    def test_slide_distance_param(self, theme, segment):
        config = AnimationConfig(strategy="slide", params={"distance": 120.0})
        item = build_word_items([segment], theme, config)[0]
        assert item.region.sample(0.0).position.y == pytest.approx(120.0)

    def test_rotate(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="rotate"))[0]
        assert item.region.sample(0.0).rotation == pytest.approx(-8.0)
        assert item.region.sample(1.0).rotation == pytest.approx(0.0)

    def test_blur(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="blur"))[0]
        assert item.region.sample(0.0).blur == pytest.approx(24.0)
        assert item.region.sample(1.0).blur == pytest.approx(0.0)

    def test_glow(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="glow"))[0]
        assert item.region.sample(0.0).glow_opacity == pytest.approx(0.0)
        assert item.region.sample(1.0).glow_opacity == pytest.approx(1.0)
        assert item.region.sample(1.0).glow_spread == pytest.approx(10.0)

    def test_pulse_oscillates(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="pulse"))[0]
        samples = [item.region.sample(t).scale.x for t in (0.2, 0.5, 0.8, 1.2, 1.6)]
        assert max(samples) > 1.05
        assert item.region.sample(2.0).scale.x == pytest.approx(1.0)

    def test_spring_overshoots_past_one(self, theme, segment):
        item = build_word_items([segment], theme, AnimationConfig(strategy="spring"))[0]
        samples = [item.region.sample(t).scale.x for t in (0.1, 0.2, 0.3, 0.4)]
        assert max(samples) > 1.0

    def test_theme_easing_flows_into_keyframes(self, segment):
        theme = resolve_theme(
            ThemeSpec(name="bounce-in", animation=AnimationPersonality(in_ease="bounce"))
        )
        item = build_word_items([segment], theme)[0]
        first = item.region.tracks[PropertyKind.OPACITY].keyframes[0]
        assert first.ease.kind == EasingKind.BOUNCE


class TestEngine:
    def test_one_item_per_word(self, theme, segment):
        items = build_word_items([segment], theme)
        assert len(items) == 2
        assert [item.text for item in items] == ["hello", "world"]

    def test_carries_emphasis(self, theme, segment):
        items = build_word_items([segment], theme)
        assert items[0].importance == pytest.approx(0.8)
        assert items[0].emphasis is EmphasisMode.HIGH
        assert items[1].emphasis is EmphasisMode.NONE

    def test_animate_segment(self, theme, segment):
        items = animate_segment(segment, theme)
        assert len(items) == 2

    def test_empty(self, theme):
        assert build_word_items([], theme) == []

    def test_deterministic(self, theme, segment):
        first = [item.model_dump() for item in build_word_items([segment], theme)]
        second = [item.model_dump() for item in build_word_items([segment], theme)]
        assert first == second

    def test_empty_words(self, theme):
        seg = Segment(text="bare", start=0.0, end=1.0)
        assert build_word_items([seg], theme) == []
