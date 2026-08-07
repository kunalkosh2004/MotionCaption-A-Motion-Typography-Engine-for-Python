import pytest

from motion_caption.easing import (
    EasingKind,
    EasingSpec,
    compile_spec,
    easing_registry,
    spring,
)


class TestEasingSpec:
    def test_preset_string(self):
        spec = EasingSpec("ease-in-out")
        assert spec.kind == "cubic-bezier"
        assert spec.params["x1"] == 0.42

    def test_kind_name_string(self):
        spec = EasingSpec("spring")
        assert spec.kind == "spring"
        assert spec.params == {}

    def test_name_dict(self):
        spec = EasingSpec({"name": "ease-out"})
        assert spec.params["x2"] == 0.58

    def test_enum(self):
        spec = EasingSpec(EasingKind.LINEAR)
        assert spec.kind == "linear"
        assert spec.params == {}

    def test_explicit_kind_params(self):
        spec = EasingSpec(kind="spring", params={"damping": 12, "frequency": 3})
        assert spec.params["damping"] == 12

    def test_kind_overrides_preset(self):
        spec = EasingSpec(EasingKind.SPRING, params={"damping": 12})
        assert spec.params["damping"] == 12

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="unknown easing preset"):
            EasingSpec("not-a-curve")

    def test_str_round_trip(self):
        assert str(EasingSpec("ease-in")) == "ease-in"
        assert str(EasingSpec("spring")) == "spring"

    def test_custom_kind_allowed(self):
        spec = EasingSpec(kind="my-custom-curve")
        assert spec.kind == "my-custom-curve"

    def test_serialization_round_trip(self):
        spec = EasingSpec("ease-in-out")
        assert EasingSpec.model_validate_json(spec.model_dump_json()) == spec


class TestFunctions:
    def test_linear(self):
        fn = compile_spec(EasingSpec("linear"))
        assert [fn(t / 10) for t in range(11)] == pytest.approx([t / 10 for t in range(11)])

    def test_endpoints_are_exact(self):
        names = (
            "ease", "ease-in", "ease-out", "ease-in-out",
            "bounce", "spring", "elastic", "overshoot",
        )
        for name in names:
            fn = compile_spec(name)
            assert fn(0.0) == pytest.approx(0.0, abs=1e-6)
            assert fn(1.0) == pytest.approx(1.0, abs=1e-2)

    def test_bezier_midpoint_symmetry(self):
        fn = compile_spec("ease-in-out")
        assert fn(0.5) == pytest.approx(0.5, abs=1e-3)

    def test_ease_in_starts_slow(self):
        fn = compile_spec("ease-in")
        assert fn(0.25) < 0.25

    def test_ease_out_ends_slow(self):
        fn = compile_spec("ease-out")
        assert fn(0.75) > 0.75

    def test_overshoot_exceeds_one(self):
        fn = compile_spec("overshoot")
        values = [fn(t / 100) for t in range(101)]
        assert max(values) > 1.0
        assert fn(1.0) == pytest.approx(1.0)

    def test_bounce_stays_in_range(self):
        fn = compile_spec("bounce")
        assert all(0.0 <= fn(t / 100) <= 1.0 for t in range(101))

    def test_spring_shape(self):
        fn = compile_spec("spring")
        assert fn(0.0) == pytest.approx(0.0)
        assert fn(1.0) == pytest.approx(1.0, abs=1e-2)
        assert fn(0.5) > 0.5

    def test_elastic_has_oscillation(self):
        fn = compile_spec(EasingSpec(kind="elastic", params={"amplitude": 1.5}))
        values = [fn(t / 100) for t in range(101)]
        transitions = sum(
            1
            for a, b in zip(values[:-1], values[1:], strict=True)
            if (b > 1.0) != (a > 1.0)
        )
        assert transitions >= 2

    def test_step_is_discrete(self):
        fn = compile_spec(EasingSpec(kind="step", params={"steps": 3}))
        values = [fn(t / 20) for t in range(21)]
        assert len(set(values)) == 4
        assert values[0] == 0.0
        assert values[-1] == 1.0

    def test_bezier_invalid_x(self):
        with pytest.raises(ValueError):
            compile_spec(
                EasingSpec(kind="cubic-bezier", params={"x1": 2, "y1": 0, "x2": 0, "y2": 1})
            )

    def test_spring_invalid_params(self):
        with pytest.raises(ValueError):
            spring(damping=0, frequency=1)


class TestRegistry:
    def test_builtins_registered(self):
        for kind in EasingKind:
            assert kind.value in easing_registry

    def test_plugin_registration(self):
        @easing_registry.register("quadratic-out")
        def factory(params):
            return lambda t: 1 - (1 - t) ** 2

        fn = compile_spec(EasingSpec(kind="quadratic-out"))
        assert fn(0.5) == pytest.approx(0.75)

    def test_unknown_kind_raises(self):
        with pytest.raises(KeyError):
            compile_spec(EasingSpec(kind="does-not-exist"))
