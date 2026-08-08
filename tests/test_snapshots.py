"""Timeline and animation snapshot tests.

The compiled ``SubtitleTimeline`` is the single source of truth for every
backend, so a byte-exact snapshot of it (and of a word's keyframed motion)
locks the whole deterministic pipeline: segmentation, emphasis, theme
resolution, typography, layout, placement and animation all feed this one
artifact. Regenerate after intentional changes with:

    MC_UPDATE_SNAPSHOTS=1 .venv/bin/python -m pytest tests/test_snapshots.py -q
"""

from __future__ import annotations

import pinned
import snapshot_utils
from motion_caption.compiler.engine import Compiler
from motion_caption.ir.timeline import SubtitleTimeline

GOLDEN_REQUEST = pinned.golden_request()


def _compile_timeline(compiler: Compiler) -> SubtitleTimeline:
    return compiler.compile(GOLDEN_REQUEST)


def test_timeline_snapshot(pinned_compiler: Compiler) -> None:
    """The full pipeline output is byte-stable for the pinned golden request."""
    timeline = _compile_timeline(pinned_compiler)

    # Structural invariants (kept even if the snapshot is regenerated).
    assert timeline.format_version == "1.0"
    assert timeline.resolution.width == 1920 and timeline.resolution.height == 1080
    assert timeline.scale == 1.0
    assert len(timeline.events) == 2
    assert len(timeline.words) == 6
    assert [event.text for event in timeline.events] == [
        "welcome to the",
        "motion typography engine",
    ]
    assert all(
        word.typography is not None and word.typography.font.family == "Roboto"
        for word in timeline.words
    )
    high = timeline.words[4]
    assert high.emphasis.value == "high"
    assert high.importance == 0.95
    karaoke = timeline.words[2]
    assert karaoke.emphasis.value == "karaoke"

    snapshot_utils.assert_text_snapshot(
        timeline.model_dump_json(indent=2) + "\n",
        "timeline",
        "golden.json",
    )


def test_timeline_snapshot_regeneration_is_idempotent(pinned_compiler: Compiler) -> None:
    """Two fresh compiles of the same request produce identical bytes."""
    assert _compile_timeline(pinned_compiler).model_dump_json() == _compile_timeline(
        pinned_compiler
    ).model_dump_json()


def test_snapshot_helpers_agree_on_missing_snapshot(pinned_compiler: Compiler) -> None:
    """The committed snapshot must exist and be up to date with the current output."""
    path = snapshot_utils.snapshot_path("timeline", "golden.json")
    assert path.is_file(), "golden timeline snapshot missing; run with MC_UPDATE_SNAPSHOTS=1"
    expected = _compile_timeline(pinned_compiler).model_dump_json(indent=2) + "\n"
    assert path.read_text(encoding="utf-8") == expected
