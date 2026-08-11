# MotionCaption

**Motion Typography Engine for Python.**

A deterministic, plugin-based compiler that turns a word-timed transcript into
professional animated captions — rendered to PNG frames or exported to
ASS / JSON, with the same compiled timeline feeding every backend.

> Not a subtitle generator. Not an AI project. An engine — the compiler of
> subtitles. Compile once, export anywhere.

```bash
pip install motion-caption
```

---

## Features

- **One request in, one timeline out.** A single serializable
  `CaptionRequest` (transcript + theme + AI annotations + platform) compiles
  to a canonical `SubtitleTimeline` — the source of truth every backend
  consumes.
- **Deterministic by construction.** Identical input produces identical
  output bytes. No hidden randomness, no LLM inside the compiler. Golden
  frames and timeline snapshots are checked into the test suite.
- **Pure, staged compiler.** `segmentation → emphasis → theme → typography →
  layout → placement → animation`. Each stage is a function of the IR, so the
  pipeline is testable and predictable.
- **Motion design, resolved.** Springs, elastic overshoot, bounce, karaoke
  fills, glow, rotation, ripple — all as keyframed animation tracks computed
  at compile time, with cubic-bezier easing families.
- **Platform-aware.** Built-in presets for YouTube Shorts, TikTok,
  Instagram Reels, landscape and square — correct resolutions, safe areas and
  face-avoiding placement.
- **AI is optional.** Rule-based segmentation and emphasis are the default.
  Add a Gemini / OpenAI provider when you want precomputed annotations
  (word emphasis, karaoke groups, theme recommendation) — the AI runs
  *outside* the compiler and never compromises determinism.
- **End-to-end video pipeline.** `caption` transcribes audio (Gemini or
  WhisperX), compiles, streams frames, overlays on the original footage and
  muxes full-quality audio — all in one command.
- **Everything plugs in.** Themes, animations, easings, exporters, placement,
  segmentation, emphasis and AI all register through a single `Registry`
  pattern and can be extended by third-party packages via entry points.

## How it works

```
CaptionRequest                  ← one serializable input (transcript, theme,
   │                               platform, safe areas, AI annotations, …)
   ▼
compiler (pure stages: segmentation → emphasis → theme → typography
   │      → layout → placement → animation)
   ▼
SubtitleTimeline                ← canonical IR, single source of truth
   │
   ├─ TimelineRenderer → RGBA PNG frames (Pillow)
   ├─ AssExporter     → .ass subtitles
   └─ JsonExporter    → JSON timeline
```

Backends never re-measure, re-layout or re-animate: everything they need is
already resolved in the IR. The compiler never touches an LLM, FFmpeg or
WhisperX — those live above it in the application layer.

## Requirements

- Python **3.12+**
- **FFmpeg** (only for the video pipeline: `caption`, `render` → video,
  `info`). Install with `brew install ffmpeg` on macOS, `apt install ffmpeg`
  on Debian/Ubuntu, or set `FFMPEG_PATH` to your binary.

### Installation

```bash
pip install motion-caption        # core compiler + renderer + exporters
pip install "motion-caption[all]" # + AI, WhisperX, face detection
```

| Extra | Adds |
|---|---|
| *(none)* | Core compiler, renderer, ASS/JSON exporters — pure Python |
| `ai` | Gemini & OpenAI annotation SDKs, Gemini transcription |
| `whisper` | WhisperX local word-level transcription (heavy: torch) |
| `video` | OpenCV face detection for face-avoiding placement |
| `all` | Everything above |

For development:

```bash
git clone https://github.com/kunalkosh2004/MotionCaption-A-Motion-Typography-Engine-for-Python
cd MotionCaption-A-Motion-Typography-Engine-for-Python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

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

For a full video (captions composited over footage with original audio), use
the end-to-end pipeline — it needs ffmpeg:

```python
from motion_caption.video import CaptionVideoPipeline

result = CaptionVideoPipeline(
    theme="music_video",
    preset="youtube_shorts",
).process("input.mp4", "output.mp4", transcript=transcript)

print(result.output_video)          # output.mp4
print(result.event_count, result.word_count, result.frames_rendered)
```

## Command line

`motion-caption` turns a video into a captioned video in one call:

```bash
motion-caption caption input.mp4 \
    --theme music_video \
    --preset youtube_shorts \
    --transcript-provider gemini \   # or whisperx; omit for offline mode
    --ai gemini \
    -o output.mp4
```

The pipeline: probe → extract audio → transcribe → [optional AI annotation] →
compile → streamed PNG frames → FFmpeg overlay → mux original audio.

Deterministic offline mode (no AI, no ASR) — just supply a transcript:

```bash
motion-caption caption input.mp4 --transcript transcript.json -o output.mp4
```

### All commands

| Command | Purpose |
|---|---|
| `motion-caption caption <video> [-o out.mp4]` | End-to-end captioned video |
| `motion-caption compile request.json [-o timeline.json]` | `CaptionRequest` → `SubtitleTimeline` |
| `motion-caption render timeline.json [--fps 30] [-o frames/]` | Timeline → PNG frame sequence |
| `motion-caption export timeline.json --format ass/json` | Timeline → `.ass` or `.json` |
| `motion-caption themes` | List built-in themes |
| `motion-caption animations` | List animation templates |
| `motion-caption exporters` | List export backends |
| `motion-caption info video.mp4` | ffprobe metadata (resolution, fps, codecs) |

Useful flags for `caption`: `--theme`, `--preset` / `--platform`, `--ai
gemini|openai`, `--transcript`, `--transcript-provider gemini|whisperx`,
`--fps`, `--resolution WxH`.

## Themes

Five built-in themes are pure data (`ThemeSpec`) — fonts are bound lazily on
first use, so nothing loads fonts at import time:

| Theme | Style | Easing personality |
|---|---|---|
| `clean` | Neutral, modern, soft shadow | default / minimal |
| `music_video` | Bold lyric captions, cyan glow | spring, elastic pop |
| `cinematic` | Elegant serif, letter-spaced gold accent | ease-out, overshoot |
| `sport` | Heavy uppercase, hard outline, yellow | overshoot, bounce |
| `news` | Editorial white-on-rounded-box | accessible |

```python
from motion_caption.themes import THEME_REGISTRY, builtin_themes, resolve_theme

print(sorted(THEME_REGISTRY.keys))          # clean, cinematic, music_video, news, sport
theme = resolve_theme(THEME_REGISTRY.get("cinematic"))
```

Themes ship with last-resort fallbacks for Indic scripts (Devanagari /
Gurmukhi) and a portable Latin fallback (DejaVu Sans), so captions resolve on
any OS — per-word glyph coverage only activates the fallback for characters
the primary stack can't draw.

## Platform presets

One name instead of five knobs — presets fill resolution, safe areas, frame
rate and placement bias on the request:

```bash
--preset youtube_shorts | tiktok | instagram_reels | youtube_landscape | square
```

```python
from motion_caption.video import available_presets, platform_preset

preset = platform_preset("youtube_shorts")   # 1080x1920, platform-safe areas
request_fields = preset.request_fields()     # platform, resolution, safe_area
```

Captions avoid platform UI chrome (safe areas) and, with face detection
enabled, faces in the footage:

```python
from motion_caption.video import CaptionVideoPipeline, OpenCVFaceDetector

pipeline = CaptionVideoPipeline(
    preset="youtube_shorts",
    theme="music_video",
    face_detector=OpenCVFaceDetector(),       # pip install "motion-caption[video]"
)
result = pipeline.process("input.mp4", "output.mp4", transcript=transcript)
```

## AI (optional)

The compiler is fully deterministic with no model in the loop. An `AIProvider`
runs *outside* the compiler and writes precomputed annotations (word
importance, emphasis modes, karaoke groups, theme recommendation) onto the
request:

```python
from motion_caption import CaptionRequest, Transcript, WordTimestamp
from motion_caption.ai import AI_REGISTRY, annotate
from motion_caption.compiler import compile

request = CaptionRequest(transcript=Transcript(words=[...]))
annotated = annotate(request, AI_REGISTRY.get("gemini"))  # reads GEMINI_API_KEY
timeline = compile(annotated)                             # still deterministic
```

Reference providers: `gemini` and `openai`, both registered in `AI_REGISTRY`.
The Gemini provider defaults to `gemini-2.5-flash`; override with
`GeminiProvider(model=...)`.

Set your key before running (nothing loads `.env` automatically):

```bash
export GEMINI_API_KEY='your-key'
```

### Transcription

Word-level transcripts come from either a local WhisperX install or Gemini:

```bash
motion-caption caption in.mp4 --transcript-provider whisperx -o out.mp4
motion-caption caption in.mp4 --transcript-provider gemini  -o out.mp4
```

When a transcript is missing and no provider is given, the pipeline fails
with a hint instead of guessing.

## The IR: `SubtitleTimeline`

The compiled timeline is the contract between compiler and backends. Every
event is fully resolved in design-space pixels — resolved typography,
keyframed animation tracks, placement regions, speaker/style tracks — so a
backends can draw or export without re-deriving anything.

```python
timeline = compile(request)
print(len(timeline.events), len(timeline.words))   # subtitle events / words
for event in timeline.events:
    print(event.start, event.end, event.text)
```

## Determinism, caching, performance

- **Determinism is a guarantee.** Same input → same bytes. Golden PNG frames
  and timeline snapshots are checked into `tests/snapshots/` (the byte-exact
  comparisons run on macOS where FreeType metrics are pinned; behavioral tests
  run everywhere).
- **Caching** lives only at composition boundaries (font loading, layout,
  frame rasterization) — never inside pure compiler stages.
- **Streaming render.** Frames are written to disk one at a time; the full
  sequence is never held in memory, so long videos stay flat on RAM.

## Extending

Everything registers through `Registry` instances: themes, animations,
easings, exporters, placement strategies, segmentation, emphasis and AI
providers. One module — `motion_caption.plugins.load_plugins()` — wires the
`motion_caption.*` entry-point groups so third-party packages can contribute
themes, animations and exporters without touching the core.

```python
from motion_caption import Registry, ThemeSpec

THEME_REGISTRY = Registry("theme")          # same registry built-ins use
THEME_REGISTRY.add("retro", my_theme_spec, overwrite=True)
```

## Animations & easings

Built-in animation templates: `none`, `fade`, `slide`, `pop`, `scale`,
`bounce`, `spring`, `elastic`, `overshoot`, `ripple`, `rotate`, `blur`,
`glow`, `karaoke`, `pulse` — used by theme personalities and overridable per
request. Easings: `linear`, cubic bezier, `spring`, `elastic`, `bounce`,
`overshoot`, `step`.

```bash
motion-caption animations   # list templates
motion-caption themes       # list themes
```

## Testing

```bash
pip install -e ".[dev]"
pytest                 # 546 tests across compiler, IR, backends, pipeline
ruff check .
```

## Documentation

- [`GUIDE.md`](GUIDE.md) — the consolidated reference: architecture, compiler
  pipeline, IR, every subsystem, backends, AI, plugins, API.
- [`docs/architecture.md`](docs/architecture.md) — design principles.
- [`docs/compiler.md`](docs/compiler.md) — compiler/IR contract.
- [`docs/video-pipeline.md`](docs/video-pipeline.md) — production video layer.
- [`docs/cli.md`](docs/cli.md) — full CLI reference.
- [`docs/integrations.md`](docs/integrations.md) — external integrations.
- [`docs/roadmap-productionization.md`](docs/roadmap-productionization.md) —
  productionization roadmap.

## License

[MIT](LICENSE)
