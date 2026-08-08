# MotionCaption

**Motion Typography Engine for Python.** A deterministic, plugin-based
compiler that turns a word-timed transcript into professional animated
captions — rendered to RGBA frames or exported to ASS / JSON, with the same
compiled timeline feeding every backend.

> Not a subtitle generator. Not an AI project. An engine: the React / LLVM /
> OpenCV of subtitles. Compile once, export anywhere.

## Status

All subsystems implemented and tested — **388 tests**, lint-clean. The
architecture is compiler-shaped:

```
CaptionRequest            ← one serializable input (transcript, theme, AI annotations, …)
   │
   ▼  compiler (pure stages: segmentation → emphasis → theme → typography
   │                       → layout → placement → animation)
SubtitleTimeline          ← canonical IR, single source of truth
   │
   ├─ TimelineRenderer    → RGBA frames (Pillow)
   ├─ AssExporter         → .ass
   └─ JsonExporter        → JSON timeline
```

Backends never re-measure, re-layout or re-animate: everything they need is
already resolved in the IR. Deterministic by construction — identical input
→ identical output bytes, which is why golden frames and timeline snapshots
are checked into the test suite.

Design contracts: [`docs/architecture.md`](docs/architecture.md) (principles
and subsystem reference) and [`docs/compiler.md`](docs/compiler.md) (the
compiler/IR contract). The [`GUIDE.md`](GUIDE.md) is the full developer
guide and API reference.

## Install

```bash
pip install -e ".[dev]"     # development
pip install motion-caption   # once published
```

Requires Python 3.12+. Optional extras: `ai` (OpenAI / Gemini providers),
`whisper` (WhisperX transcript import).

## Quick start

```python
from motion_caption import Canvas, CaptionRequest, Transcript, WordTimestamp
from motion_caption.compiler import compile
from motion_caption.exporters import EXPORTER_REGISTRY
from motion_caption.render import TimelineRenderer

# 1. One serializable request: word-timed transcript + theme name.
request = CaptionRequest(
    transcript=Transcript(
        words=[
            WordTimestamp(text="hello", start=0.0, end=0.6),
            WordTimestamp(text="motion", start=0.7, end=1.4),
            WordTimestamp(text="typography", start=1.5, end=2.2),
        ]
    ),
    theme="music_video",          # a ThemeSpec, a registry name, or None
)

# 2. Compile once.
timeline = compile(request)

# 3. Any backend consumes the same timeline.
frame = TimelineRenderer().render_frame(
    timeline, t=1.0, canvas=Canvas.from_standard("1080p")
)
frame.save("frame.png")

ass = EXPORTER_REGISTRY.get("ass").export(timeline).data
open("captions.ass", "w", encoding="utf-8").write(ass)

json_timeline = EXPORTER_REGISTRY.get("json").export(timeline).data
```

## Backward-compatible facades

The pre-compiler APIs keep working and now compile internally:

```python
from motion_caption import CaptionRenderer, RenderOptions, resolve_theme, build_ass

canvas = Canvas.from_standard("1080p")
theme = resolve_theme(load_theme("clean"))
segments = [...]                       # Segment/Word objects as before
frame = CaptionRenderer().render_frame(segments, theme, ctx, canvas, t=1.0)
ass_text = build_ass(segments, theme, ctx, canvas, options=AssOptions())
```

## AI is optional

The compiler is fully deterministic with no model in the loop. An
`AIProvider` (OpenAI / Gemini reference implementations in
`motion_caption.ai`) runs *outside* the compiler and writes precomputed
annotations (importance, emphasis, word-group splits, theme recommendation)
onto the request:

```python
from motion_caption.ai import annotate, AI_REGISTRY

annotated = annotate(request, AI_REGISTRY.get("openai"))  # needs an API key
timeline = compile(annotated)
```

Without a provider, rule-based segmentation and emphasis are the fallback.

## Extending

Everything registers through `Registry` instances (themes, animations,
easings, exporters, placements, segmentation, emphasis, AI). One module —
`motion_caption.plugins.load_plugins()` — wires the `motion_caption.*`
entry-point groups for third-party packages. See `GUIDE.md` and
`docs/compiler.md` §7.
