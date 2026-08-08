"""Plugin aggregation: the single place that wires entry-point groups.

Every pluggable subsystem exposes a ``Registry``; this module is the only
place that maps importlib entry-point groups to them (docs/compiler.md §7).
``load_plugins`` is explicitly opt-in — nothing is scanned at import time.
"""

from __future__ import annotations

from collections.abc import Iterable

from motion_caption.ai import AI_REGISTRY
from motion_caption.animations.templates import ANIMATION_REGISTRY
from motion_caption.easing.functions import easing_registry
from motion_caption.emphasis.engine import EMPHASIS_REGISTRY
from motion_caption.exporters import EXPORTER_REGISTRY
from motion_caption.placement.engine import PLACEMENT_REGISTRY
from motion_caption.registry import Registry
from motion_caption.segmentation.engine import SEGMENTATION_REGISTRY
from motion_caption.themes.catalog import THEME_REGISTRY

PLUGIN_GROUPS: dict[str, Registry] = {
    "motion_caption.themes": THEME_REGISTRY,
    "motion_caption.animations": ANIMATION_REGISTRY,
    "motion_caption.easings": easing_registry,
    "motion_caption.exporters": EXPORTER_REGISTRY,
    "motion_caption.placements": PLACEMENT_REGISTRY,
    "motion_caption.segmentation": SEGMENTATION_REGISTRY,
    "motion_caption.emphasis": EMPHASIS_REGISTRY,
    "motion_caption.ai": AI_REGISTRY,
}


def load_plugins(groups: Iterable[str] | None = None) -> int:
    """Load third-party plugins from entry-point groups (default: all groups).

    Returns the total number of plugins registered. Entry-point plugins may
    overwrite built-ins (``Registry.load_entry_points`` uses ``overwrite=True``)
    and repeated calls are safe.
    """
    if groups is None:
        selected = PLUGIN_GROUPS
    else:
        selected = {}
        for group in groups:
            registry = PLUGIN_GROUPS.get(group)
            if registry is None:
                available = ", ".join(sorted(PLUGIN_GROUPS))
                raise KeyError(
                    f"no entry-point group {group!r}; available: {available}"
                )
            selected[group] = registry
    total = 0
    for group, registry in selected.items():
        total += registry.load_entry_points(group)
    return total
