"""Tests for the plugin aggregation module."""

from __future__ import annotations

import pytest

from motion_caption.animations.templates import ANIMATION_REGISTRY
from motion_caption.easing.functions import easing_registry
from motion_caption.emphasis.engine import EMPHASIS_REGISTRY
from motion_caption.exporters import EXPORTER_REGISTRY
from motion_caption.placement.engine import PLACEMENT_REGISTRY
from motion_caption.plugins import PLUGIN_GROUPS, load_plugins
from motion_caption.registry import Registry
from motion_caption.segmentation.engine import SEGMENTATION_REGISTRY
from motion_caption.themes.catalog import THEME_REGISTRY


def test_all_groups_are_wired():
    expected = {
        "motion_caption.themes": THEME_REGISTRY,
        "motion_caption.animations": ANIMATION_REGISTRY,
        "motion_caption.easings": easing_registry,
        "motion_caption.exporters": EXPORTER_REGISTRY,
        "motion_caption.placements": PLACEMENT_REGISTRY,
        "motion_caption.segmentation": SEGMENTATION_REGISTRY,
        "motion_caption.emphasis": EMPHASIS_REGISTRY,
    }
    assert expected == PLUGIN_GROUPS
    for registry in PLUGIN_GROUPS.values():
        assert isinstance(registry, Registry)


def test_load_plugins_no_third_party_is_idempotent():
    # No third-party entry points are installed, so this loads zero plugins
    # without raising, and repeated calls are safe.
    assert load_plugins() == 0
    assert load_plugins() == 0


def test_load_plugins_selected_group():
    assert load_plugins(groups=["motion_caption.easings"]) == 0
    with pytest.raises(KeyError, match="available"):
        load_plugins(groups=["motion_caption.unknown"])


def test_builtins_survive_loading():
    load_plugins()
    assert "clean" in THEME_REGISTRY
    assert "fade" in ANIMATION_REGISTRY
    assert "linear" in easing_registry
    assert "ass" in EXPORTER_REGISTRY
    assert "bottom" in PLACEMENT_REGISTRY
    assert "sentence" in SEGMENTATION_REGISTRY
    assert "rules" in EMPHASIS_REGISTRY
