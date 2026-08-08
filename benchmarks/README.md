# Benchmarks

`bench.py` is a standalone micro-benchmark for the deterministic pipeline:
`CaptionRequest → SubtitleTimeline` (compile), then the two IR backends
(`TimelineRenderer` frames and the ASS/JSON exporters).

It reuses the **pinned-font harness** (`tests/pinned.py` — deliberately
pytest-free), so every stage runs against the bundled Roboto and measures
pipeline cost, not font discovery. Timing is a **median of runs after
warmup** to ignore one-off catalog/cache warm-up.

## Run

```sh
.venv/bin/python benchmarks/bench.py              # defaults: 60 words, 50 iters
.venv/bin/python benchmarks/bench.py --words 120 --iterations 100
```

## Stages

| Stage | What it measures |
|---|---|
| `compile-cold` | A fresh `CaptionRequest` per run — the full stage pipeline, no cache hits. |
| `compile-warm` | The same request repeated — timeline-cache hits. |
| `frame` | One 1080p RGBA frame through the dumb `TimelineRenderer`. |
| `sequence(1s@30)` | 31 frames (1 s at 30 fps). |
| `export-ass` / `export-json` | Serializing the compiled timeline through each backend. |

The numbers are for relative regression tracking — compare commits, not
machines. A meaningful guardrail: `compile-warm` and `frame` should both be
well under one millisecond on any modern laptop.

Two honest caveats:

- `compile-warm` is *not* a pure cache lookup: `Compiler` re-serializes the
  request (`model_dump_json`) to compute the cache-key digest on every call,
  so that cost is included in the number.
- `export-ass` has been the slowest stage on this machine (~60 ms for 60
  words / 15 events) — a known hotspot worth profiling if ASS export ever
  needs to be interactive.
