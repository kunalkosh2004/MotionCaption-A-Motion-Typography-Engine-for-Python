#!/usr/bin/env python
"""Micro-benchmarks for the compile → export / render pipeline.

Runs the same pinned-font golden pipeline the snapshot tests use, then times
each stage in steady state (median of ``--iterations`` runs after warmup):

- ``compile-cold``  — a fresh ``CaptionRequest`` per run (no cache reuse)
- ``compile-warm``  — the same request repeated (timeline cache hits)
- ``frame``         — one 1080p frame through ``TimelineRenderer``
- ``sequence``      — a 1 s render at 30 fps (31 frames)
- ``export-ass``    — the compiled timeline through the ASS backend
- ``export-json``   — the compiled timeline through the JSON backend

Usage:
    .venv/bin/python benchmarks/bench.py [--iterations N] [--words N]
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path

# Plain scripts don't get the pytest ``pythonpath`` setting, so wire up
# ``src`` (the package) and ``tests`` (the pytest-free pinned helpers) here.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "tests"))

import pinned  # noqa: E402
from motion_caption.canvas import Canvas  # noqa: E402
from motion_caption.exporters import EXPORTER_REGISTRY  # noqa: E402
from motion_caption.ir.request import AIContribution, CaptionRequest  # noqa: E402
from motion_caption.ir.timeline import SubtitleTimeline  # noqa: E402
from motion_caption.models.transcript import Transcript, WordTimestamp  # noqa: E402
from motion_caption.render.timeline import TimelineRenderer  # noqa: E402

DEFAULT_WORDS = 60
DEFAULT_ITERATIONS = 50


def build_request(word_count: int = DEFAULT_WORDS, *, fresh: bool = False) -> CaptionRequest:
    """A request with ``word_count`` words grouped into 4-word captions.

    ``fresh=True`` makes the request digest unique so the compiler's timeline
    cache never hits — that is the "cold compile" path.
    """
    span = 0.45
    words = [
        WordTimestamp(text=f"word{index}", start=index * span, end=(index + 1) * span)
        for index in range(word_count)
    ]
    return CaptionRequest(
        metadata={"bench": True, "run": time.time_ns() if fresh else 0},
        transcript=Transcript(words=words),
        theme=pinned.pinned_theme_spec(),
        llm_annotations=AIContribution(
            importance={word_count - 1: 0.95},
            splits=[
                list(range(start, min(start + 4, word_count)))
                for start in range(0, word_count, 4)
            ],
        ),
    )


def median_ms(fn: Callable[[], object], iterations: int) -> float:
    """Steady-state median wall time of ``fn`` in milliseconds."""
    for _ in range(3):  # warmup
        fn()
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(samples)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--words", type=int, default=DEFAULT_WORDS)
    args = parser.parse_args()

    compiler = pinned.pinned_compiler()
    request = build_request(args.words)
    timeline = compiler.compile(request)
    assert isinstance(timeline, SubtitleTimeline)

    renderer = TimelineRenderer()
    canvas = Canvas.from_standard("1080p")
    ass_exporter = EXPORTER_REGISTRY.get("ass")
    json_exporter = EXPORTER_REGISTRY.get("json")

    rows = [
        (
            "compile-cold",
            args.iterations,
            median_ms(
                lambda: compiler.compile(build_request(args.words, fresh=True)),
                args.iterations,
            ),
        ),
        (
            "compile-warm",
            args.iterations * 10,
            median_ms(lambda: compiler.compile(request), args.iterations * 10),
        ),
        (
            "frame",
            args.iterations,
            median_ms(lambda: renderer.render_frame(timeline, 12.0, canvas), args.iterations),
        ),
        (
            "sequence(1s@30)",
            max(3, args.iterations // 5),
            median_ms(
                lambda: renderer.render_sequence(timeline, canvas, start=0.0, end=1.0),
                max(3, args.iterations // 5),
            ),
        ),
        (
            "export-ass",
            args.iterations * 4,
            median_ms(lambda: ass_exporter.export(timeline), args.iterations * 4),
        ),
        (
            "export-json",
            args.iterations * 4,
            median_ms(lambda: json_exporter.export(timeline), args.iterations * 4),
        ),
    ]

    print(f"pipeline benchmark: {args.words} words | {len(timeline.events)} events | 1080p")
    print(f"{'stage':<16}{'iters':>8}{'median ms':>12}{'ops/s':>12}")
    for label, iterations, millis in rows:
        ops_per_sec = 1000.0 / millis
        print(f"{label:<16}{iterations:>8}{millis:>12.3f}{ops_per_sec:>12.1f}")


if __name__ == "__main__":
    main()
