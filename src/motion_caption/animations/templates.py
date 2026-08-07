"""Named animation templates: theme personality → per-word keyframe timelines.

A template is a pure function from a ``TemplateContext`` (word timing, theme
easings, config knobs) to a ``RegionTimeline`` — the canonical sampled-anim
model. All motion goes through the theme's easing identities (``in``, ``out``,
``pop``, ``idle``). Third parties register new templates via
``ANIMATION_REGISTRY``.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from motion_caption.easing.spec import EasingSpec
from motion_caption.models.geometry import Point
from motion_caption.models.keyframe import (
    Keyframe,
    KeyframeTimeline,
    PropertyKind,
    RegionTimeline,
)
from motion_caption.models.transcript import EmphasisMode
from motion_caption.registry import Registry

type Template = Callable[["TemplateContext"], RegionTimeline]


class TemplateContext(BaseModel):
    """Everything a template needs to build a timeline for one word."""

    start: float
    end: float
    emphasis: EmphasisMode = EmphasisMode.NONE
    easings: dict[str, EasingSpec] = Field(default_factory=dict)
    in_window: float = Field(default=0.2, gt=0.0, le=1.0)
    out_window: float = Field(default=0.15, gt=0.0, le=1.0)
    params: dict[str, float] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def in_end(self) -> float:
        hold = 1.0 - self.out_window
        return min(
            self.start + self.duration * self.in_window,
            self.start + self.duration * hold,
        )

    @property
    def out_start(self) -> float:
        return max(self.end - self.duration * self.out_window, self.in_end)


def _fade_track(ctx: TemplateContext, *, max_opacity: float = 1.0) -> KeyframeTimeline:
    return KeyframeTimeline(
        kind=PropertyKind.OPACITY,
        keyframes=[
            Keyframe(ctx.start, 0.0, ctx.easings["in"]),
            Keyframe(ctx.in_end, max_opacity, ctx.easings["in"]),
            Keyframe(ctx.out_start, max_opacity, ctx.easings["out"]),
            Keyframe(ctx.end, 0.0, ctx.easings["out"]),
        ],
    )


def _hold_track(
    ctx: TemplateContext, kind: PropertyKind, value: float
) -> KeyframeTimeline:
    return KeyframeTimeline(
        kind=kind,
        keyframes=[Keyframe(ctx.start, value), Keyframe(ctx.end, value)],
    )


def _scale_entrance_track(
    ctx: TemplateContext, from_scale: float, *, exit_scale: float = 0.9
) -> KeyframeTimeline:
    return KeyframeTimeline(
        kind=PropertyKind.SCALE,
        keyframes=[
            Keyframe(ctx.start, from_scale, ctx.easings["pop"]),
            Keyframe(ctx.in_end, 1.0, ctx.easings["pop"]),
            Keyframe(ctx.out_start, 1.0, ctx.easings["out"]),
            Keyframe(ctx.end, exit_scale, ctx.easings["out"]),
        ],
    )


def _overshoot_scale_track(
    ctx: TemplateContext,
    *,
    start: float,
    peak: float,
    settle: float,
    exit_scale: float,
) -> KeyframeTimeline:
    return KeyframeTimeline(
        kind=PropertyKind.SCALE,
        keyframes=[
            Keyframe(ctx.start, start, ctx.easings["pop"]),
            Keyframe(ctx.in_end, peak, ctx.easings["pop"]),
            Keyframe(ctx.in_end + ctx.duration * 0.3, settle, ctx.easings["pop"]),
            Keyframe(ctx.out_start, settle, ctx.easings["out"]),
            Keyframe(ctx.end, exit_scale, ctx.easings["out"]),
        ],
    )


def static(ctx: TemplateContext) -> RegionTimeline:
    return RegionTimeline().add_track(_hold_track(ctx, PropertyKind.OPACITY, 1.0))


def fade(ctx: TemplateContext) -> RegionTimeline:
    return RegionTimeline().add_track(_fade_track(ctx))


def slide(ctx: TemplateContext) -> RegionTimeline:
    distance = ctx.params.get("distance", 60.0)
    ease_in, ease_out = ctx.easings["in"], ctx.easings["out"]
    track = KeyframeTimeline(
        kind=PropertyKind.POSITION,
        keyframes=[
            Keyframe(ctx.start, Point(0.0, distance), ease_in),
            Keyframe(ctx.in_end, Point(0.0, 0.0), ease_in),
            Keyframe(ctx.out_start, Point(0.0, 0.0), ease_out),
            Keyframe(ctx.end, Point(0.0, distance), ease_out),
        ],
    )
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(track)


def pop(ctx: TemplateContext) -> RegionTimeline:
    start = ctx.params.get("start_scale", 0.6)
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(
        _scale_entrance_track(ctx, start)
    )


def scale(ctx: TemplateContext) -> RegionTimeline:
    start = ctx.params.get("start_scale", 0.85)
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(
        _scale_entrance_track(ctx, start, exit_scale=1.0)
    )


def bounce(ctx: TemplateContext) -> RegionTimeline:
    start = ctx.params.get("start_scale", 0.5)
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(
        _scale_entrance_track(ctx, start)
    )


def spring(ctx: TemplateContext) -> RegionTimeline:
    start = ctx.params.get("start_scale", 0.4)
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(
        _scale_entrance_track(ctx, start)
    )


def elastic(ctx: TemplateContext) -> RegionTimeline:
    start = ctx.params.get("start_scale", 0.2)
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(
        _scale_entrance_track(ctx, start)
    )


def overshoot(ctx: TemplateContext) -> RegionTimeline:
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(
        _overshoot_scale_track(
            ctx,
            start=ctx.params.get("start_scale", 0.5),
            peak=ctx.params.get("peak_scale", 1.15),
            settle=ctx.params.get("settle_scale", 1.0),
            exit_scale=ctx.params.get("exit_scale", 0.9),
        )
    )


def ripple(ctx: TemplateContext) -> RegionTimeline:
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(
        _overshoot_scale_track(
            ctx,
            start=ctx.params.get("start_scale", 0.7),
            peak=ctx.params.get("peak_scale", 1.2),
            settle=ctx.params.get("settle_scale", 1.0),
            exit_scale=ctx.params.get("exit_scale", 0.95),
        )
    )


def rotate(ctx: TemplateContext) -> RegionTimeline:
    degrees = ctx.params.get("degrees", -8.0)
    track = KeyframeTimeline(
        kind=PropertyKind.ROTATION,
        keyframes=[
            Keyframe(ctx.start, degrees, ctx.easings["pop"]),
            Keyframe(ctx.in_end, 0.0, ctx.easings["pop"]),
            Keyframe(ctx.out_start, 0.0, ctx.easings["out"]),
            Keyframe(ctx.end, degrees, ctx.easings["out"]),
        ],
    )
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(track)


def blur(ctx: TemplateContext) -> RegionTimeline:
    amount = ctx.params.get("blur", 24.0)
    track = KeyframeTimeline(
        kind=PropertyKind.BLUR,
        keyframes=[
            Keyframe(ctx.start, amount, ctx.easings["in"]),
            Keyframe(ctx.in_end, 0.0, ctx.easings["in"]),
            Keyframe(ctx.out_start, 0.0, ctx.easings["out"]),
            Keyframe(ctx.end, amount, ctx.easings["out"]),
        ],
    )
    return RegionTimeline().add_track(_fade_track(ctx)).add_track(track)


def glow(ctx: TemplateContext) -> RegionTimeline:
    spread = ctx.params.get("spread", 10.0)
    max_opacity = ctx.params.get("glow_opacity", 1.0)
    ease_in, ease_out = ctx.easings["in"], ctx.easings["out"]
    spread_track = KeyframeTimeline(
        kind=PropertyKind.GLOW_SPREAD,
        keyframes=[
            Keyframe(ctx.start, 0.0, ease_in),
            Keyframe(ctx.in_end, spread, ease_in),
            Keyframe(ctx.out_start, spread, ease_out),
            Keyframe(ctx.end, 0.0, ease_out),
        ],
    )
    opacity_track = KeyframeTimeline(
        kind=PropertyKind.GLOW_OPACITY,
        keyframes=[
            Keyframe(ctx.start, 0.0, ease_in),
            Keyframe(ctx.in_end, max_opacity, ease_in),
            Keyframe(ctx.out_start, max_opacity, ease_out),
            Keyframe(ctx.end, 0.0, ease_out),
        ],
    )
    return (
        RegionTimeline()
        .add_track(_fade_track(ctx))
        .add_track(spread_track)
        .add_track(opacity_track)
    )


def karaoke(ctx: TemplateContext) -> RegionTimeline:
    quick = ctx.model_copy(update={"in_window": 0.35, "out_window": 0.3})
    return RegionTimeline().add_track(_fade_track(quick)).add_track(
        _scale_entrance_track(quick, 0.9, exit_scale=1.0)
    )


def pulse(ctx: TemplateContext) -> RegionTimeline:
    scale_boost = ctx.params.get("pulse_scale", 0.12)
    period = ctx.params.get("pulse_period", 0.25)
    result = RegionTimeline().add_track(_fade_track(ctx))
    keyframes = [Keyframe(ctx.start, 1.0, ctx.easings["pop"])]
    step = ctx.duration * period
    cursor = ctx.in_end
    while step > 0.0 and cursor < ctx.out_start:
        keyframes.append(Keyframe(cursor, 1.0 + scale_boost, ctx.easings["pop"]))
        cursor += step
        keyframes.append(Keyframe(min(cursor, ctx.out_start), 1.0, ctx.easings["pop"]))
        cursor += step
    keyframes.append(Keyframe(ctx.out_start, 1.0, ctx.easings["out"]))
    keyframes.append(Keyframe(ctx.end, 1.0, ctx.easings["out"]))
    return result.add_track(
        KeyframeTimeline(kind=PropertyKind.SCALE, keyframes=keyframes)
    )


ANIMATION_REGISTRY: Registry[Template] = Registry("animation")

ANIMATION_REGISTRY.add("none", static, aliases=("static",), overwrite=True)
ANIMATION_REGISTRY.add("fade", fade, overwrite=True)
ANIMATION_REGISTRY.add("slide", slide, overwrite=True)
ANIMATION_REGISTRY.add("pop", pop, overwrite=True)
ANIMATION_REGISTRY.add("scale", scale, overwrite=True)
ANIMATION_REGISTRY.add("bounce", bounce, overwrite=True)
ANIMATION_REGISTRY.add("spring", spring, overwrite=True)
ANIMATION_REGISTRY.add("elastic", elastic, overwrite=True)
ANIMATION_REGISTRY.add("overshoot", overshoot, overwrite=True)
ANIMATION_REGISTRY.add("ripple", ripple, overwrite=True)
ANIMATION_REGISTRY.add("rotate", rotate, overwrite=True)
ANIMATION_REGISTRY.add("blur", blur, overwrite=True)
ANIMATION_REGISTRY.add("glow", glow, overwrite=True)
ANIMATION_REGISTRY.add("karaoke", karaoke, overwrite=True)
ANIMATION_REGISTRY.add("pulse", pulse, overwrite=True)
