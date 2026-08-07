"""Serializable easing specification.

Pure data (no MotionCaption dependencies): a ``kind`` plus free parameters.
The ``kind`` is a free-form string so plugins can register custom easing
functions under new keys without extending the built-in enum.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EasingKind(StrEnum):
    """Built-in easing families."""

    LINEAR = "linear"
    CUBIC_BEZIER = "cubic-bezier"
    SPRING = "spring"
    ELASTIC = "elastic"
    BOUNCE = "bounce"
    OVERSHOOT = "overshoot"
    STEP = "step"


_PRESETS: dict[str, dict[str, object]] = {
    "linear": {"kind": EasingKind.LINEAR.value, "params": {}},
    "ease": {
        "kind": EasingKind.CUBIC_BEZIER.value,
        "params": {"x1": 0.25, "y1": 0.1, "x2": 0.25, "y2": 1.0},
    },
    "ease-in": {
        "kind": EasingKind.CUBIC_BEZIER.value,
        "params": {"x1": 0.42, "y1": 0.0, "x2": 1.0, "y2": 1.0},
    },
    "ease-out": {
        "kind": EasingKind.CUBIC_BEZIER.value,
        "params": {"x1": 0.0, "y1": 0.0, "x2": 0.58, "y2": 1.0},
    },
    "ease-in-out": {
        "kind": EasingKind.CUBIC_BEZIER.value,
        "params": {"x1": 0.42, "y1": 0.0, "x2": 0.58, "y2": 1.0},
    },
}


class EasingSpec(BaseModel):
    """A serializable easing curve reference.

    Buildable from a named preset string (``EasingSpec("ease-in-out")``), a
    ``{name: ...}`` dict, an ``EasingKind`` enum (for built-ins), or an
    explicit ``{kind, params}`` dict.
    """

    kind: str = EasingKind.LINEAR.value
    params: dict[str, float] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

    def __init__(self, value: object = None, **data: object) -> None:
        """Ergonomically accept ``EasingSpec("ease-in-out")`` or explicit kwargs."""
        if value is not None:
            merged = dict(self._coerce(value))
            merged.update(data)
            data = merged
        super().__init__(**data)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if isinstance(data, EasingSpec):
            return data
        if isinstance(data, EasingKind):
            return {"kind": data.value, "params": {}}
        if isinstance(data, str):
            if data not in _PRESETS:
                if data in EasingKind._value2member_map_:
                    return {"kind": data, "params": {}}
                available = ", ".join(sorted(_PRESETS))
                raise ValueError(f"unknown easing preset {data!r}; available: {available}")
            return dict(_PRESETS[data])
        if isinstance(data, dict):
            if "name" in data:
                name = data["name"]
                if name not in _PRESETS:
                    available = ", ".join(sorted(_PRESETS))
                    raise ValueError(f"unknown easing preset {name!r}; available: {available}")
                preset = dict(_PRESETS[name])
                preset.update({k: v for k, v in data.items() if k != "name"})
                return preset
            return data
        raise ValueError(f"cannot build EasingSpec from {data!r}")

    @classmethod
    def named(cls, name: str) -> EasingSpec:
        return cls.model_validate(name)

    def __str__(self) -> str:
        for name, preset in _PRESETS.items():
            if preset.get("kind") == self.kind and preset.get("params") == self.params:
                return name
        if not self.params:
            return self.kind
        params = ", ".join(f"{k}={v:g}" for k, v in self.params.items())
        return f"{self.kind}({params})"
