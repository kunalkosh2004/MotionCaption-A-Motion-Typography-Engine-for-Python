# MotionCaption Architecture

MotionCaption is a **motion typography engine** for Python: a deterministic,
plugin-based system that turns a word-timed transcript into professional
animated subtitles for video editors.

This document is the design contract. Every subsystem is implemented against
it. Nothing here is decorative.

---

## 1. Mission and Non-Goals

**Mission.** Be the substrate that editors build on — the "React / Pillow /
OpenCV for subtitles." A reusable library, installable via
`pip install motion-caption`, embeddable, headless, deterministic.

**Non-goals (explicit).**

- No LLM required. AI is an optional plugin layer over a fully deterministic
  pipeline. The renderer never talks to a model.
- No subtitle *generation* (transcribing audio). We consume word-timed
  transcripts; WhisperX etc. are optional inputs.
- No frontend, no JavaScript, no servers.
- No GPU/WebGPU *yet* — but the architecture must not forbid it.

**The split.**

| Decides | System |
|---|---|
| important words, emotion, theme, segmentation | AI (optional plugins) |
| typography, layout, placement, animation, timing interpolation, rendering | MotionCaption (deterministic) |

---

## 2. Design Principles

1. **Semantics are separate from rendering.** The internal object graph is
   semantic (transcript → segments → words → keyframed regions). Exporters
   interpret that graph. One graph, many outputs (ASS, PNG, JSON, FFmpeg).
2. **Everything is keyframes.** Every subtitle becomes a small timeline of
   keyframed properties (position, scale, rotation, opacity, color, blur,
   stroke, shadow) interpolated by easing functions. This is the single source
   of truth; it is why determinism and multiple exporters are free.
3. **Purity before speed.** Subsystems are pure functions over models. Caching
   and parallelism are added at composition boundaries, never inside core logic.
4. **Open for extension, closed for modification.** New themes, animations,
   easings, exporters, placement strategies and AI providers register
   themselves. Core code never knows a concrete plugin.
5. **Resolution independence is a first-class unit system.** All lengths are
   typed (`px`, `em`, `%`, `vw`, `vh`) and resolved against a design space.
6. **Determinism is a guarantee.** No RNG, no wall-clock, no iteration-order
   dependence. Identical input → identical output bytes.

---

## 3. Layers (Clean Architecture)

Dependency arrows point inward. The `models/` layer has zero dependencies on
the rest of the package.

```
┌─────────────────────────────────────────────────────────────────┐
│  Composition root: CaptionEngine, CLI                            │
├─────────────────────────────────────────────────────────────────┤
│  Interface layer: plugins/ (Registry + entry points)            │
│   ── themes, animations, exporters, placements, ai providers    │
├─────────────────────────────────────────────────────────────────┤
│  Application layer (pure logic, no I/O)                         │
│   segmentation · emphasis · reading · easing · animation        │
│   layout · placement · safe-area                                │
├─────────────────────────────────────────────────────────────────┤
│  Domain layer: models/  (units, geometry, color, transcript,    │
│   keyframe, canvas)  — Pydantic value objects + entities        │
└─────────────────────────────────────────────────────────────────┘
  Infrastructure: typography (fonttools/Pillow), renderer (Pillow),
  exporters (ASS/JSON/FFmpeg/PNG), ai (SDK clients)
```

Every box exports a narrow public interface; nothing reaches across layers.

### Package layout

```
motion_caption/
    models/        # pure value objects & entities (units, geometry, color,
                   # transcript, canvas, keyframe)
    easing/        # interpolation functions (linear, cubic-bezier, spring,
                   # elastic, bounce, overshoot) — pure math
    typography/    # font catalog/fallback/loading, text styles, measurement
    segmentation/  # transcript → subtitle segments (grammar, rhythm, reading)
    emphasis/      # word importance scoring (rule-based + AI override)
    reading/       # reading speed, difficulty, density analysis
    animation/     # keyframe timelines → animated property curves
    layout/        # measured blocks → positioned, aligned regions
    placement/     # safe areas, platform UI avoidance, face-aware placement
    themes/        # theme model + built-in theme catalog (30+)
    renderer/      # rasterization and compositing (Pillow/numpy)
    exporters/     # ASS, JSON timeline, FFmpeg filters, PNG sequence
    plugins/       # Registry + importlib entry-point loading
    ai/            # provider protocols (Gemini/OpenAI/Claude/local)
    cli/           # argparse CLI
    utils/         # shared cache/threading/parallel helpers
    engine.py      # CaptionEngine — composition root, public API
    registry.py    # Registry base class
    canvas.py      # Canvas + standard resolutions
```

Empty directories are only created when their subsystem lands, in roadmap order.

---

## 4. Rendering Pipeline

The pipeline is a linear chain of pure transforms. Each stage reads models,
writes models; the final stage alone touches I/O.

```
Transcript (JSON, word-timed)
   │
   ▼
[1] segmentation      → list[Segment]              (grammar/phrase/rhythm-aware)
   ▼
[2] emphasis          → Segment with per-word importance scores
   ▼
[3] reading           → per-segment duration, line length, pacing adjusted
   ▼
[4] typography+layout → MeasuredBlock per segment, positioned on canvas
   ▼
[5] animation         → per-word KeyframeTimeline (theme-driven)
   ▼
[6] placement         → safe-area + face-aware final regions
   ▼
[7] render            → sample timeline → raster frames (Pillow/numpy)
   ▼
[8] export            → ASS / JSON / FFmpeg filter / PNG sequence
```

Stage 7 is the only rasterizer; exporters 8 reinterpret the sampled timeline
(ASS expresses animation via override tags and `\t` segments; PNG bakes it).

### The keyframe object model (canonical)

```python
class PropertyKind(Enum): POSITION, ROTATION, SCALE, OPACITY,
                          COLOR, BLUR, STROKE, SHADOW, LETTER_SPACING

class Keyframe(BaseModel):
    time: float
    value: Animatable          # Float | Point | Color | ...
    ease: EasingSpec           # named curve + parameters (e.g. spring 0.9)

class KeyframeTimeline(BaseModel):
    kind: PropertyKind
    keyframes: list[Keyframe]
    def sample(self, t) -> Animatable: ...   # deterministic interpolation

class WordItem(BaseModel):     # one animated word
    text, start, end
    importance: float
    region: RegionTimeline     # composition of PropertyTimelines
```

`RegionTimeline.sample(t)` yields a `Region` (position, scale, rotation,
opacity, color, blur, stroke, shadow) — a plain snapshot the renderer draws
and exporters translate. Rendering is *sampling*, never per-frame authoring.

---

## 5. Core Abstractions

### 5.1 Models (`models/`)

- `units.py` — `Length(value, unit)` with `px/em/%/vw/vh`; `Resolution`;
  `DesignSpace(reference, scale_policy)`; `ResolutionContext` (canvas +
  design + font size) used to resolve lengths at render time.
- `geometry.py` — `Point`, `Size`, `Box`, `Padding` (length-based).
- `color.py` — `Color` (RGBA), `GradientStop`, `GradientFill`, `FillSpec`.
- `transcript.py` — `Transcript`, `WordTimestamp`, `Word`, `Segment`,
  `EmphasisMode`.
- `keyframe.py` — the canonical animation model (future phase).
- `canvas.py` — `Canvas`, `AspectRatio`, `StandardResolution`
  (720p/1080p/2K/4K/portrait/landscape/square/shorts).

### 5.2 Registry (`registry.py`)

A tiny, thread-safe generic registry. Plugins register under a key with
optional aliases; entry-point groups extend it at runtime:

```python
themes = Registry[Type[Theme]]("theme")

@themes.register("music_video")
class MusicVideoTheme(Theme): ...

themes.load_entry_points("motion_caption.themes")   # third-party themes
```

Entry-point groups (declared for future subsystems):

| Group | Registers |
|---|---|
| `motion_caption.themes` | Theme classes |
| `motion_caption.animations` | Animation strategy classes |
| `motion_caption.easings` | Easing functions |
| `motion_caption.exporters` | Exporter classes |
| `motion_caption.placements` | Placement strategy classes |
| `motion_caption.ai` | AI provider classes |

### 5.3 Resolution model

Typography is authored in **design units** against a reference resolution
(default 1920×1080). At render time `ResolutionContext` maps units to output
pixels:

- `px` → `value × scale` where scale = min/max ratio of canvas:reference
  (COVER/FIT policy). Subtitle size, padding, radius all scale together.
- `em` → `value × current font size` (self-relative; used for tracking,
  line-height).
- `%` → fraction of the reference frame's minor dimension.
- `vw` / `vh` → fraction of the output canvas.

Same style renders correctly on 720p, 4K, 1080×1920 and 1080×1080 without
rebuilding the style.

---

## 6. Subsystem Reference

Each subsystem: **responsibility**, **key abstractions**, **extensibility**.

### typography
Font discovery (system dirs + user dirs), weight/italic matching, font
fallback per character (via fonttools cmap), Pillow-based deterministic
measurement (per-glyph advances + tracking), style model (fill, stroke,
shadow, glow, background box, radius, padding, blur, opacity, uppercase),
greedy line wrapping into `MeasuredBlock`.
*Extensible via:* custom `FontCatalog`/`FontManager`, new `Length` units.

### segmentation
Grammar/phrase/rhythm-aware splitter. Bounded by `max_words`,
`max_duration`, `min_duration`, reading-speed targets. Never raw character
counts. Multi-language via language-aware phrase rules.
*Extensible via:* `SegmentationStrategy` plugins; AI may propose splits.

### emphasis
Rule-based scorer (positions, parts-of-speech, filler-word list, repetition)
returns 0..1 importance per word. AI provider may override scores.
*Extensible via:* `EmphasisScorer` plugins; `ai` provider protocol.

### reading
Computes words-per-second, difficulty, and density; adjusts segment
durations, line lengths, and animation timing so on-screen text stays
readable.

### easing
Pure functions `(t: 0..1) -> eased`, including named cubic-beziers
(ease-in/out/in-out), spring, elastic, bounce, overshoot. Compiled into
`EasingSpec` for serialization.
*Extensible via:* `motion_caption.easings` entry point.

### animation
Builds `KeyframeTimeline`s from theme "animation templates" (pop, fade,
scale, bounce, spring, elastic, slide, blur, rotate, glow, karaoke, pulse,
overshoot, ripple). All interpolation goes through easing.
*Extensible via:* `motion_caption.animations` entry points.

### layout / placement
Measured blocks are positioned with margins/padding/alignment; placement
applies safe-area insets (TikTok, IG Reels, Shorts, landscape, square) and
face-aware avoidance (never over eyes/mouth/face; dynamic repositioning;
multi-speaker; portrait framing).
*Extensible via:* `motion_caption.placements` strategies.

### themes
A `Theme` declares font stack, colors, stroke/shadow/highlight, animation
style, padding, margins, line height, reading speed, background style —
the full semantic-to-render mapping. Themes are plain data (JSON) plus an
optional code hook. Built-in catalog ships 30+ production themes.
*Extensible via:* registry + `Theme.from_file()` for user themes.

### renderer / exporters
Renderer samples keyframe timelines and rasterizes with Pillow + numpy.
Exporters reinterpret the same timeline:
- **ASS** — text + override tags (`\fscx`, `\alpha`, `\blur`, `\t` with
  baked acceleration segments).
- **JSON** — full keyframe timeline (for editors, web previews).
- **FFmpeg** — filter graph (drawtext/subtitles chains, burned-in).
- **PNG sequence** — baked frames.
*Extensible via:* `Exporter` protocol + `motion_caption.exporters` entry
point. Future: Lottie, SVG, WebGPU/Canvas via the same timeline → new
interpreters, no core changes.

### ai
A `Protocol` with `annotate(transcript, context) -> AIContribution`
(importance, emotion, segmentation, theme suggestion). Deterministic
fallbacks run when no provider is configured. Providers are never imported
by core.

---

## 7. Determinism Guarantees

- No `random`, no `time()`/`datetime.now()` in core paths.
- Registries iterate in registration order; plugin keys are stable.
- Easing/measure functions are pure; floats are rounded at exporter
  boundaries with documented precision.
- `LC_ALL`-independent parsing; no locale-aware formatting in core.
- Same version + same input files → byte-identical output.

---

## 8. Performance Strategy

- **Caching:** font metadata, cmap coverage, Pillow font handles, and
  measured blocks (LRU) are cached per resolution/size.
- **Lazy loading:** fonts and theme files load on first use; nothing is
  scanned at import time.
- **Parallel rendering:** timeline sampling and rasterization are
  embarrassingly parallel per segment/batch — `ProcessPoolExecutor` at the
  composition boundary.
- **Memory:** streams frames in chunks; never materializes hour-long videos
  or thousands of rasterized subtitle frames at once.
- **Numerics:** numpy-vectorized sampling for large timelines.

---

## 9. Implementation Roadmap

Build order follows dependency direction; each phase ships tested and
reviewed before the next begins.

1. ✅ Architecture (this doc) + scaffold
2. ✅ Core models: units, geometry, color, transcript, canvas, registry
3. ✅ Typography engine: fonts, styles, measurement
4. Easing + keyframe engine (canonical animation model)
5. Theme engine + built-in theme catalog
6. Segmentation engine
7. Emphasis (rule-based) + reading engine
8. Layout + placement (safe areas, face-aware)
9. Animation strategies → keyframe timelines
10. Renderer (Pillow/numpy) + ASS exporter
11. JSON timeline, FFmpeg filter, PNG sequence exporters
12. AI provider protocol + reference plugins
13. CLI + docs + benchmarks

---

## 10. Trade-off Log (decisions, revisited as we build)

| Decision | Why | Cost |
|---|---|---|
| Keyframes as canonical truth | single source → determinism, all exporters free | exporters must interpret curves (e.g. ASS `\t` baking) |
| Pydantic everywhere | strict validation, serialization to/from JSON for editors & AI | object overhead (mitigated by caching) |
| CSS-like `Length` units | resolution independence without rebuilding styles | resolver complexity |
| fonttools for coverage | real per-char fallback, accurate weight matching | a small pure-Python dependency |
| Greedy (not Knuth-Plass) wrapping | deterministic, fast, predictable for editors | occasionally suboptimal breaks (improved by segmentation, which is our real wrap control) |
| Plugin registry (not ABC discovery) | explicit, debuggable, entry-point compatible | user must know plugin names |
| Pure pipeline stages | easy to test, cache, parallelize | boilerplate at composition boundary |

---

## 11. Public API (target shape)

```python
from motion_caption import CaptionEngine

engine = CaptionEngine(theme="music_video")
engine.render(transcript="words.json", output="captions.ass")

# or programmatic
from motion_caption import CaptionEngine, Theme

theme = Theme(...)
engine = CaptionEngine(theme)
```
