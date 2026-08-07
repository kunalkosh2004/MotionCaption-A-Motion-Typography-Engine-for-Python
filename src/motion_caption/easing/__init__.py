"""Easing subsystem: serializable specs, deterministic functions, registry."""

from motion_caption.easing.functions import (
    EasingFunction,
    bounce,
    compile_spec,
    cubic_bezier,
    easing_registry,
    elastic,
    linear,
    overshoot,
    spring,
    step,
)
from motion_caption.easing.spec import EasingKind, EasingSpec

__all__ = [
    "EasingFunction",
    "EasingKind",
    "EasingSpec",
    "bounce",
    "compile_spec",
    "cubic_bezier",
    "easing_registry",
    "elastic",
    "linear",
    "overshoot",
    "spring",
    "step",
]
