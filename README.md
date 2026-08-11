# MotionCaption

**Motion Typography Engine for Python.** A deterministic, plugin-based
compiler that turns a word-timed transcript into professional animated
captions — rendered to RGBA frames or exported to ASS / JSON, with the same
compiled timeline feeding every backend.

> Not a subtitle generator. Not an AI project. An engine: the React / LLVM /
> OpenCV of subtitles. Compile once, export anywhere.

## Status

All subsystems implemented and tested — **499 tests**, lint-clean. The
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

**How it works:** the single consolidated reference is
[`GUIDE.md`](GUIDE.md) — architecture, compiler pipeline, IR, every
subsystem, backends, AI, plugins, and the full API reference in one file.
The design contracts live in [`docs/architecture.md`](docs/architecture.md)
(principles) and [`docs/compiler.md`](docs/compiler.md) (the compiler/IR
contract). The production video pipeline is in
[`docs/video-pipeline.md`](docs/video-pipeline.md), external integrations in
[`docs/integrations.md`](docs/integrations.md), and the productionization
roadmap in [`docs/roadmap-productionization.md`](docs/roadmap-productionization.md).

## Install

```bash
pip install -e ".[dev]"     # development (compiler + test tooling)
pip install motion-caption   # once published
```

Requires Python 3.12+ and FFmpeg for the video pipeline. Optional extras:

| Extra | Adds |
|---|---|
| `ai` | Gemini / OpenAI annotation SDKs; Gemini transcription |
| `whisper` | WhisperX word-level transcription (heavy: torch) |
| `video` | OpenCV face detection for the video pipeline |
| `all` | everything above |
| `dev` | pytest, pytest-cov, ruff |

## Command line

`motion-caption` turns a video into a captioned video in one call
(transcribe → compile → streamed render → FFmpeg encode → audio mux):

```bash
motion-caption caption input.mp4 \
    --theme music_video \
    --preset youtube_shorts \
    --ai gemini \
    --transcript-provider gemini \   # or whisperx; omit for offline mode
    -o output.mp4
```

Omit `--theme` and the transcript provider can pick one for you — with Gemini
transcription the model recommends a theme from the lyrics' vibe (fallback:
`clean`).

Deterministic offline mode (no AI, no ASR):

```bash
motion-caption caption input.mp4 --transcript transcript.json -o output.mp4
```

Plus `compile` (request JSON → timeline JSON), `render` (timeline → PNG
frames), `export` (timeline → ASS/JSON), `themes` / `animations` /
`exporters` (listings) and `info` (ffprobe metadata). Full reference in
[`docs/cli.md`](docs/cli.md).

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
from motion_caption import (
    AssOptions,
    Canvas,
    CaptionRenderer,
    ResolutionContext,
    build_ass,
    load_theme,
    resolve_theme,
)

canvas = Canvas.from_standard("1080p")
ctx = ResolutionContext(canvas=canvas.resolution)
theme = resolve_theme(load_theme("clean"))
segments = [...]                       # Segment/Word objects as before
frame = CaptionRenderer().render_frame(segments, theme, ctx, canvas, t=1.0)
ass_text = build_ass(segments, theme, ctx, canvas, options=AssOptions())
```

(Full runnable versions of both paths are in `GUIDE.md` §3.)

## AI is optional

The compiler is fully deterministic with no model in the loop. An
`AIProvider` (OpenAI / Gemini reference implementations in
`motion_caption.ai`) runs *outside* the compiler and writes precomputed
annotations (importance, emphasis, word-group splits, theme recommendation)
onto the request:

```python
from motion_caption.ai import annotate, AI_REGISTRY

annotated = annotate(request, AI_REGISTRY.get("gemini"))  # reads GEMINI_API_KEY
timeline = compile(annotated)
```

Set the key before running (nothing loads `.env` automatically):

```bash
echo 'GEMINI_API_KEY=your-key' > .env   # .env is gitignored
set -a; source .env; set +a
```

`GeminiProvider` defaults to `gemini-2.5-flash` (some keys carry no quota on
older models); override with `GeminiProvider(model=...)`. Without a
provider, rule-based segmentation and emphasis are the fallback.

## Extending

Everything registers through `Registry` instances (themes, animations,
easings, exporters, placements, segmentation, emphasis, AI). One module —
`motion_caption.plugins.load_plugins()` — wires the `motion_caption.*`
entry-point groups for third-party packages. See `GUIDE.md` and
`docs/compiler.md` §7.
