"""Timeline and animation snapshot tests.

The compiled ``SubtitleTimeline`` is the single source of truth for every
backend, so a byte-exact snapshot of it (and of a word's keyframed motion)
locks the whole deterministic pipeline: segmentation, emphasis, theme
resolution, typography, layout, placement and animation all feed this one
artifact. Regenerate after intentional changes with:

    MC_UPDATE_SNAPSHOTS=1 .venv/bin/python -m pytest tests/test_snapshots.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pinned
import snapshot_utils
from motion_caption.compiler.engine import Compiler
from motion_caption.ir.timeline import SubtitleTimeline, WordEvent
from motion_caption.models.keyframe import Region

GOLDEN_REQUEST = pinned.golden_request()

REPO_ROOT = Path(__file__).resolve().parents[1]


def _portable(value: str) -> str:
    """Normalize absolute repo paths so snapshots are byte-stable on any checkout.

    ``WordEvent``/``StyleTrack`` typography serializes the bound font's
    ``FontFile.path`` as an absolute path; replace the repo root with a
    placeholder so the committed snapshot does not depend on where the
    repository lives on disk.
    """
    return value.replace(str(REPO_ROOT), "<REPO_ROOT>")


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
        _portable(timeline.model_dump_json(indent=2)) + "\n",
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
    expected = _portable(_compile_timeline(pinned_compiler).model_dump_json(indent=2)) + "\n"
    assert path.read_text(encoding="utf-8") == expected


def _animation_times(word: WordEvent) -> list[float]:
    """Fixed-t sample points across the word's lifespan (held outside)."""
    start = float(word.start)
    end = float(word.end)
    span = end - start
    return [start + span * fraction for fraction in (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0)]


def test_animation_track_snapshot(pinned_compiler: Compiler) -> None:
    """The HIGH-emphasis word's keyframe tracks are byte-stable."""
    word = _compile_timeline(pinned_compiler).words[4]
    assert word.animation is not None and not word.animation.is_static()
    assert sorted(track.kind.value for track in word.animation.tracks.values()) == [
        "opacity",
        "scale",
    ]
    snapshot_utils.assert_text_snapshot(
        word.animation.model_dump_json(indent=2) + "\n",
        "animation",
        "golden_track.json",
    )


def test_animation_curve_snapshot(pinned_compiler: Compiler) -> None:
    """Sampling the motion at fixed times lands on a stable curve."""
    word = _compile_timeline(pinned_compiler).words[4]
    samples = [word.region_at(t) for t in _animation_times(word)]
    assert all(isinstance(sample, Region) for sample in samples)
    assert all(sample.opacity >= 0.0 and sample.opacity <= 1.0 for sample in samples)
    payload = (
        json.dumps([sample.model_dump(mode="json") for sample in samples], indent=2) + "\n"
    )
    snapshot_utils.assert_text_snapshot(payload, "animation", "golden_samples.json")
