"""Deterministic easing functions and their plugin registry.

Every function is pure math: ``(t: 0..1) -> eased``. No RNG, no wall-clock,
no state. Built-ins register themselves under their ``EasingKind`` key;
third parties register new keys through the same registry.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from motion_caption.easing.spec import EasingKind, EasingSpec
from motion_caption.registry import Registry

EasingFunction = Callable[[float], float]
EasingFactory = Callable[[dict[str, float]], EasingFunction]


def _clamp01(t: float) -> float:
    return min(1.0, max(0.0, t))


def linear(t: float) -> float:
    return t


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> EasingFunction:
    """Standard cubic bezier easing (CSS-style), solved for x."""
    if not (0.0 <= x1 <= 1.0 and 0.0 <= x2 <= 1.0):
        raise ValueError("cubic-bezier control x values must be in [0, 1]")

    def bezier_x(t: float) -> float:
        return 3.0 * (1 - t) ** 2 * t * x1 + 3.0 * (1 - t) * t**2 * x2 + t**3

    def bezier_y(t: float) -> float:
        return 3.0 * (1 - t) ** 2 * t * y1 + 3.0 * (1 - t) * t**2 * y2 + t**3

    def derivative_x(t: float) -> float:
        return 3.0 * (1 - t) ** 2 * x1 + 6.0 * (1 - t) * t * (x2 - x1) + 3.0 * t**2 * (1 - x2)

    def solve_x(x: float) -> float:
        t = x
        for _ in range(8):  # Newton-Raphson
            error = bezier_x(t) - x
            if abs(error) < 1e-7:
                return t
            slope = derivative_x(t)
            if abs(slope) < 1e-7:
                break
            t = min(1.0, max(0.0, t - error / slope))
        lo, hi = 0.0, 1.0  # bisection fallback
        t = x
        for _ in range(24):
            if bezier_x(t) < x:
                lo = t
            else:
                hi = t
            t = (lo + hi) / 2.0
        return t

    def ease(t: float) -> float:
        t = _clamp01(t)
        if t == 0.0 or t == 1.0:
            return t
        return bezier_y(solve_x(t))

    return ease


def spring(damping: float = 8.0, frequency: float = 2.0) -> EasingFunction:
    """Damped harmonic oscillator settling at 1 (overshoots when damping is low)."""
    if damping <= 0.0 or frequency <= 0.0:
        raise ValueError("spring damping and frequency must be positive")

    def ease(t: float) -> float:
        t = _clamp01(t)
        return 1.0 - math.exp(-damping * t) * math.cos(math.pi * frequency * t)

    return ease


def elastic(amplitude: float = 1.0, period: float = 0.3) -> EasingFunction:
    """Decaying oscillation that overshoots both ends before settling."""
    if amplitude < 0.0 or period <= 0.0:
        raise ValueError("elastic amplitude must be >= 0 and period must be positive")

    def ease(t: float) -> float:
        t = _clamp01(t)
        if t == 0.0 or t == 1.0:
            return t
        s = (
            period / 4.0
            if amplitude < 1.0
            else period / (2.0 * math.pi) * math.asin(1.0 / amplitude)
        )
        u = t - 1.0
        return -amplitude * math.pow(2.0, 10.0 * u) * math.sin((u - s) * 2.0 * math.pi / period)

    return ease


def bounce(t: float) -> float:
    """Classic ease-out bounce (three landings), from easings.net."""
    t = _clamp01(t)
    n1, d1 = 7.5625, 2.75
    if t < 1.0 / d1:
        return n1 * t * t
    if t < 2.0 / d1:
        u = t - 1.5 / d1
        return n1 * u * u + 0.75
    if t < 2.5 / d1:
        u = t - 2.25 / d1
        return n1 * u * u + 0.9375
    u = t - 2.625 / d1
    return n1 * u * u + 0.984375


def overshoot(amount: float = 1.70158) -> EasingFunction:
    """Back-ease: overshoots past 1 then settles (amount = overshoot strength)."""

    def ease(t: float) -> float:
        t = _clamp01(t)
        if t == 0.0 or t == 1.0:
            return t
        u = t - 1.0
        return u * u * ((amount + 1.0) * u + amount) + 1.0

    return ease


def step(steps: int = 1) -> EasingFunction:
    """Discrete step function (for karaoke fills and frame holds)."""
    n = max(1, int(steps))

    def ease(t: float) -> float:
        t = _clamp01(t)
        return min(1.0, math.floor(t * (n + 1)) / n)

    return ease


# The registry is the plugin seam: keyed by free-form string, seeded with the
# built-in families. Third-party easings register new keys via
# ``easing_registry.register("my-curve")(factory)``.
easing_registry: Registry[EasingFactory] = Registry("easing")

easing_registry.add(EasingKind.LINEAR.value, lambda params: linear, overwrite=True)
easing_registry.add(
    EasingKind.CUBIC_BEZIER.value,
    lambda p: cubic_bezier(
        p.get("x1", 0.25), p.get("y1", 0.1), p.get("x2", 0.25), p.get("y2", 1.0)
    ),
    overwrite=True,
)
easing_registry.add(
    EasingKind.SPRING.value,
    lambda p: spring(p.get("damping", 8.0), p.get("frequency", 2.0)),
    overwrite=True,
)
easing_registry.add(
    EasingKind.ELASTIC.value,
    lambda p: elastic(p.get("amplitude", 1.0), p.get("period", 0.3)),
    overwrite=True,
)
easing_registry.add(EasingKind.BOUNCE.value, lambda p: bounce, overwrite=True)
easing_registry.add(
    EasingKind.OVERSHOOT.value,
    lambda p: overshoot(p.get("amount", 1.70158)),
    overwrite=True,
)
easing_registry.add(
    EasingKind.STEP.value,
    lambda p: step(int(p.get("steps", 1))),
    overwrite=True,
)


def compile_spec(spec: EasingSpec | str) -> EasingFunction:
    """Resolve an easing spec (or preset name) to a callable function."""
    resolved = EasingSpec.model_validate(spec) if isinstance(spec, str) else spec
    factory = easing_registry.get(resolved.kind)
    return factory(resolved.params)
