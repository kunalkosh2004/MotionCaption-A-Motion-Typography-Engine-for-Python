# MotionCaption — How It Works

**MotionCaption** is a deterministic, plugin-based **motion typography engine**
for Python. It turns a word-timed transcript (WhisperX-style) into
professional, animated captions — rendered to RGBA image sequences via
Pillow, or exported directly to `.ass` / JSON.

> One serializable input. One canonical intermediate representation. Many
> backends. Everything is deterministic: identical input → identical output
> bytes.

This document is the **single how-it-works reference**: the architecture,
the compiler pipeline, the IR, every subsystem, the backends, the AI seam,
the plugin system, the guarantees, and the complete API.

---

## 1. The Big Picture

MotionCaption behaves like a **compiler**:

```
CaptionRequest            ← one serializable input
   │
   ▼
[0] normalize             defaults: canvas, design, options, theme lookup
[1] segment               Transcript → list[Segment]   (SEGMENTATION_REGISTRY)
[2] emphasize             per-word importance + EmphasisMode (EMPHASIS_REGISTRY)
[3] pace                  extend ends for reading speed  (reading engine)
[4] resolve theme         ResolvedTheme (CompiledThemeCache; fonts resolved)
[5] resolve typography    base ResolvedTypography + per-emphasis deltas
[6] measure + layout      MeasuredBlock → PlacedBlock (speaker-aware)
[7] animate               per-word AnimationTrack      (ANIMATION_REGISTRY)
[8] place                 safe area + face-aware + speaker bias → PlacementRegion
[9] assemble              SubtitleTimeline (IR)         (compile cache)
   │
   ▼
SubtitleTimeline          ← canonical IR, single source of truth
   │
   ├─ TimelineRenderer    → RGBA frames (Pillow)
   ├─ AssExporter         → .ass
   └─ JsonExporter        → JSON timeline
```

The compiler analogy runs through every decision:

| Concept | MotionCaption |
|---|---|
| Source program | `CaptionRequest` |
| Lexer / parser | segmentation |
| Semantic analysis | emphasis + reading |
| Frontend passes | theme → typography → layout → placement |
| Canonical IR | `SubtitleTimeline` |
| Backends | exporters (ASS, JSON, …) |

**The one rule that makes everything work:** `SubtitleTimeline` is the single
source of truth. Every compiler stage reads the request and writes the
timeline; every backend reads the timeline and writes bytes. **No backend
ever measures text, picks fonts, lays out, or animates** — everything is
already resolved inside the IR.

---

## 2. The Input: `CaptionRequest`

One serializable object is the input to every public API.

```python
class CaptionRequest(BaseModel):
    metadata: dict[str, Any] = {}          # title, episode, language, job id, ...
    transcript: Transcript                 # word-timed words
    faces: list[Face] = []                 # face boxes for avoidance
    safe_area: SafeArea | None = None
    platform: str | None = None            # "tiktok", "youtube_shorts", ...
    theme: ThemeSpec | str | None = None   # spec, or registry name
    llm_annotations: AIContribution | None = None   # optional, precomputed
    speaker_tracks: list[SpeakerTrack] = []
    resolution: Resolution | StandardResolution | str | None = None
    design: DesignSpace | None = None      # default 1920x1080 COVER
    options: CompileOptions | None = None  # segmentation/animation/layout/...
    future_extensions: dict[str, Any] = {}
```

Design decisions:

- **`theme` accepts a name or a spec.** A `ThemeSpec` is data (JSON); a name
  is data too. Because the compiler resolves it, a request can carry a name
  and be serialized — exactly what an AI theme recommendation or an editor
  round-trip needs.
- **`llm_annotations` is an *input*, not a live call.** AI runs *outside* the
  deterministic compiler; its output is precomputed data attached to the
  request. This keeps the pipeline pure, replayable, and SDK-free.
- **`resolution` is optional with a default.** The compiler produces a
  timeline in *design-space pixels* (see §4), so the timeline stays
  resolution-independent and can be re-exported at any size.
- **`future_extensions` is a free-form dict.** Unplanned inputs (audio
  features, brand colors, per-platform overrides) enter without a breaking
  change.

### `AIContribution` (the only AI shape)

```python
class AIContribution(BaseModel):           # lives in motion_caption.ir
    importance: dict[int, float] | None = None      # word index -> 0..1
    emphasis: dict[int, EmphasisMode] | None = None
    splits: list[list[int]] | None = None           # word-index groups
    theme: str | None = None                        # recommended theme name
    emotion: str | None = None
```

### `SpeakerTrack`

```python
class SpeakerTrack(BaseModel):
    id: str
    word_indices: list[int] = []     # indices into transcript.words
    bias: float = 0.0                # vertical bias for this speaker's captions
```

Placement uses `bias` to stack speakers vertically; `word_indices` maps
transcript words to a speaker so each `SubtitleEvent` can be tagged.

---

## 3. The Compiler Pipeline

Every stage is a pure function over a `CompileContext` (the "stage bus" that
carries the request, enriched segments, `ResolvedTheme`, resolved typography,
placed blocks, word items, and the final timeline). Stages only read/write
fields they own, and are individually replaceable.

| # | Stage | Does | Registry / engine |
|---|---|---|---|
| 0 | normalize | defaults: canvas, design, options, theme name lookup | — |
| 1 | segment | transcript → `Segment` blocks, grammar/rhythm-aware | `SEGMENTATION_REGISTRY` |
| 2 | emphasize | importance 0..1 → `EmphasisMode` per word | `EMPHASIS_REGISTRY` |
| 3 | pace | extend ends so text stays readable | reading engine |
| 4 | resolve theme | bind fonts + easing identities → `ResolvedTheme` | `THEME_REGISTRY` + `CompiledThemeCache` |
| 5 | typography | every `Length` → design px; `ResolvedTypography` | typography engine |
| 6 | measure + layout | measure → wrap → align → `PlacedBlock` | layout engine |
| 7 | animate | per-word `AnimationTrack` keyframes | `ANIMATION_REGISTRY` |
| 8 | place | safe areas + face avoidance + speaker bias | `PLACEMENT_REGISTRY` |
| 9 | assemble | `SubtitleTimeline` | compile cache |

Key separation rules:

- **Typography is separate from layout** (5 vs 6). Layout does measurement,
  wrapping, alignment, positioning — nothing else. Typography answers "what
  does the text look like"; layout answers "where do the glyphs go". They
  meet only at `ResolvedTypography`.
- **Placement is last and only about position.** Safe areas, face avoidance,
  speaker stacking, portrait/landscape. It never touches style or motion.
- **The renderer never sees a theme.** It consumes `ResolvedTypography` +
  `AnimationTrack` only.

---

## 4. The IR: `SubtitleTimeline`

The IR is **pure data**. It imports only `models/` primitives (`Point`,
`Box`, `Color`, `Keyframe`, `KeyframeTimeline`, `PropertyKind`, `Region`)
and `typing` — **not** themes, fonts, layout or placement code. That makes it
serializable to JSON byte-for-byte and deterministic by construction.

```
SubtitleTimeline
 ├── format_version: "1.0"
 ├── metadata: dict
 ├── resolution: Resolution            # the canvas the compile targeted
 ├── design: DesignSpace
 ├── scale: float                      # design px -> output px (policy-driven)
 ├── styles: list[StyleTrack]          # interned block-level styles
 └── tracks: list[Track]               # one per speaker/layer
      └── SubtitleEvent                # one caption on screen
           ├── start / end / text
           ├── style: StyleTrack       # block typography (filled in)
           ├── region: PlacementRegion # where it sits
           ├── speaker: str | None
           ├── layer: int
           └── words: list[WordEvent]
                ├── text / start / end / importance / emphasis
                ├── box: Box           # measured bounds, design px, absolute
                ├── typography: ResolvedTypography   # word-level (emphasis deltas)
                └── animation: AnimationTrack        # keyframed motion -> Region
```

### 4.1 `ResolvedTypography`

A `TextStyle` with every `Length` resolved to a float in design-space pixels,
and fonts resolved to concrete faces. This is the object the renderer draws
from — the renderer **never resolves a length again**.

```python
class ResolvedFont(BaseModel):
    family: str          # for ASS fontname
    weight: int          # for ASS bold
    italic: bool
    path: str            # for Pillow
    index: int           # face index inside TTC

class ResolvedTypography(BaseModel):
    font: ResolvedFont
    font_size: float
    fill: Color
    fill_gradient: GradientFill | None = None
    stroke: ResolvedStroke | None = None      # width/color/opacity (px)
    shadow: ResolvedShadow | None = None      # offset/blur/color/opacity (px)
    glow: ResolvedGlow | None = None          # color/spread/opacity (px)
    background: ResolvedBackground | None = None
    letter_spacing: float
    word_spacing: float
    line_height: float
    opacity: float
    blur: float
    uppercase: bool
    align: TextAlign
```

Why floats and not `Length`? Because `Length` resolution requires a
`ResolutionContext`; once the typography stage resolves, everything downstream
is pure math. An exporter or rasterizer must never re-resolve typography.

### 4.2 Motion: `KeyframeTrack`, `AnimationTrack`, `Region`

```python
class KeyframeTrack(BaseModel):
    kind: PropertyKind
    timeline: KeyframeTimeline        # ordered keyframes + deterministic sample()

class AnimationTrack(BaseModel):
    tracks: dict[PropertyKind, KeyframeTrack]
    phases: dict[str, tuple[float, float]] = {}   # "in"/"out"/"idle" spans
    def sample(self, t: float) -> Region: ...     # composition -> Region
```

`Region` is the existing sampled snapshot from `models.keyframe`: position,
scale, rotation, opacity, color, blur, stroke, shadow — a plain snapshot the
renderer draws and exporters translate. **Rendering is *sampling*, never
per-frame authoring.**

### 4.3 Placement and lanes

```python
class PlacementRegion(BaseModel):
    box: Box                   # absolute bounds, design px
    anchor: Point              # layout anchor (usually box center)
    speaker: str | None
    layer: int = 0

class Track(BaseModel):
    name: str
    speaker: str | None
    events: list[SubtitleEvent] = []
```

`Track` is the "lane": one per speaker or layer. Exporters may flatten
(`timeline.events`) or keep lanes for multi-speaker styling.

### 4.4 Why the IR stores *resolved design-space* pixels

The timeline is compiled at the request's `design.reference` resolution
(1920×1080 by default). `timeline.scale` maps design px → output px for the
requested canvas. Consequences:

- **Compile once, export everywhere.** One `SubtitleTimeline` renders to
  720p, 4K and portrait by multiplying by `scale` — no re-measure, no rebuild.
- **Deterministic by construction.** No target-dependent state in the IR.
- **Caches are small and canvas-independent.** Measurement/layout/animation
  caches are keyed on design px, so one 1080p compile feeds all outputs.

---

## 5. Every Subsystem, Explained

### 5.0 The Registry pattern (everything plugs in)

All subsystems register through `motion_caption.registry.Registry` — a tiny,
thread-safe registry with aliases and entry-point loading:

```python
themes = Registry[Type[Theme]]("theme")

@themes.register("music_video")          # or add(name, obj, overwrite=...)
class MusicVideoTheme(Theme): ...

themes.load_entry_points("motion_caption.themes")   # third-party themes
```

Dispatch is always `registry.get(key)(...)` — **no switch statements, no
giant registries anywhere.** The built-in registries:

| Registry | Import from | Built-ins |
|---|---|---|
| `THEME_REGISTRY` | `motion_caption.themes` | `clean`, `music_video`, `cinematic`, `sport`, `news`, `default` |
| `easing_registry` | `motion_caption.easing` | `linear`, `step`, `cubic-bezier`, `spring`, `bounce`, `elastic`, `overshoot` |
| `ANIMATION_REGISTRY` | `motion_caption.animations` | `none`, `fade`, `slide`, `pop`, `scale`, `bounce`, `spring`, `elastic`, `overshoot`, `ripple`, `rotate`, `blur`, `glow`, `karaoke`, `pulse` |
| `PLACEMENT_REGISTRY` | `motion_caption.placement` | `bottom`, `top`, `center`, `face-aware` |
| `SEGMENTATION_REGISTRY` | `motion_caption.segmentation` | `sentence`, `pauses`, `strict` |
| `EMPHASIS_REGISTRY` | `motion_caption.emphasis` | `rules` |
| `EXPORTER_REGISTRY` | `motion_caption.exporters` | `ass`, `json` |
| `AI_REGISTRY` | `motion_caption.ai` | `openai`, `gemini` |

### 5.1 Segmentation (`motion_caption.segmentation`)

Grammar / phrase / rhythm-aware splitter. Bounded by `max_words`,
`max_duration`, `min_duration` and reading-speed targets — never raw
character counts. Multi-language via language-aware phrase rules.
*Extensible via:* `SegmentationStrategy` plugins; AI may propose splits
(`AIContribution.splits`).

### 5.2 Emphasis (`motion_caption.emphasis`)

Rule-based scorer (positions, parts-of-speech, filler-word list, repetition)
returns a 0..1 importance per word; `importance_to_mode(score)` maps that to
`EmphasisMode` (`none`/`low`/`medium`/`high`/`karaoke`). AI may override
scores. *Extensible via:* `EmphasisScorer` plugins; the AI provider protocol.

### 5.3 Reading (`motion_caption.reading`)

Computes words-per-second, difficulty, and density; `adjust_segments` tunes
segment durations and line lengths so on-screen text stays readable.

### 5.4 Easing (`motion_caption.easing`)

Pure functions `(t: 0..1) -> eased`, including `linear`, `step`, `cubic-bezier`
(named presets), `spring`, `elastic`, `bounce`, and `overshoot`.
`compile_spec(EasingSpec) -> EasingFunction` turns a serializable spec into a
callable — themes reference easings by identity, never by implementation.
*Extensible via:* the `motion_caption.easings` entry point.

### 5.5 Animation (`motion_caption.animations`)

Builds `KeyframeTimeline`s from theme "animation templates" (pop, fade,
scale, bounce, spring, elastic, slide, blur, rotate, glow, karaoke, pulse,
overshoot, ripple). All interpolation goes through easing. The output is
per-word keyframe timelines — never direct image manipulation.
*Extensible via:* the `motion_caption.animations` entry point.

### 5.6 Themes (`motion_caption.themes`)

A `ThemeSpec` declares the full semantic-to-render mapping: font stack,
colors, stroke/shadow/highlight, animation personality, padding, margins,
line height, reading speed, background style. Themes are plain data (JSON).
`resolve_theme(spec, font_manager=None) -> ResolvedTheme` binds them to
concrete fonts and compiled easings — and is cached by the compiler.
*Extensible via:* `THEME_REGISTRY` + `Theme.from_file()` for user themes.

### 5.7 Typography (`motion_caption.typography`)

Font discovery (system + user dirs), weight/italic matching, per-character
font fallback (via fontTools cmap), Pillow-based deterministic measurement
(per-glyph advances + tracking), and the style model (fill, stroke, shadow,
glow, background box, radius, padding, blur, opacity, uppercase). Greedy line
wrapping into `MeasuredBlock`.
*Extensible via:* custom `FontCatalog`/`FontManager`, new `Length` units.

### 5.8 Layout (`motion_caption.layout`)

Only measurement, wrapping, alignment, positioning. `LayoutEngine` is the
measure → wrap → position facade; `lay_out(block, canvas, options, ctx)`
returns a `PlacedBlock` at absolute canvas coordinates. It never calculates
typography.

### 5.9 Placement (`motion_caption.placement`)

Only decides *where* captions appear: safe-area insets (TikTok, IG Reels,
Shorts, landscape, square), face-aware avoidance (never over eyes/mouth/face;
dynamic repositioning; portrait framing), and multi-speaker vertical stacking
via `SpeakerTrack.bias`. *Extensible via:* `PLACEMENT_REGISTRY` strategies.

### 5.10 Units & geometry (`motion_caption.models`)

CSS-like typed lengths: `Length(value, unit)` with `px/em/%/vw/vh`,
resolved against a `DesignSpace` via `ResolutionContext`. `px` scales with
canvas:reference ratio (COVER/FIT policy); `em` is font-relative; `%` is
fraction of the frame's minor dimension; `vw`/`vh` are canvas fractions.
Same style renders correctly on 720p, 4K, 1080×1920 and 1080×1080 **without
rebuilding the style**.

---

## 6. Backends: Renderer and Exporters

### 6.1 `TimelineRenderer` (dumb rasterizer)

Given `SubtitleTimeline`, `t`, and a target canvas it (a) finds overlapping
`SubtitleEvent`s, (b) samples each `AnimationTrack` → `Region`, (c)
composites glyphs with `ResolvedTypography` at `region.position + word.box *
scale`. It does **not** measure, choose fonts, compute layout, or know themes
exist. `TimelineRenderer.render_frame(timeline, t, canvas)` /
`render_sequence(timeline, canvas, fps=30)` are the two entry points.

### 6.2 `CaptionRenderer` (backward-compatible facade)

The original segment/theme API keeps its exact signatures; it now compiles a
`CaptionRequest` internally and delegates to `TimelineRenderer`. Nobody's
existing code breaks — the implementation moved behind the compiler.

### 6.3 The `Exporter` contract

```python
class Exporter(Protocol):
    name: str
    def export(self, timeline: SubtitleTimeline) -> ExporterResult: ...

@dataclass(frozen=True)
class ExporterResult:
    data: str | bytes
    media_type: str = "text/plain"   # "application/json", "image/png", ...
    extension: str = "txt"
```

Every exporter consumes **only** `SubtitleTimeline`. Implementations may
accept extra keyword options (e.g. `AssExporter.export(timeline, *, fps=30,
style_name="Default")`), but a call with only `timeline` must always succeed.
Dispatch is `EXPORTER_REGISTRY.get(name).export(timeline)` — no switch
statements. The `motion_caption.exporters` entry-point group loads
third-party backends.

**Shipped backends:**

- **ASS** — re-expressed as a consumer of the IR. It bakes `\t` override
  segments by sampling `AnimationTrack` (the correct "interpreter" behavior),
  but reads positions/colors/fonts from `WordEvent`/`ResolvedTypography`.
- **JSON** — free: the IR is already pydantic; `model_dump_json` with
  rounding at documented precision.

Future interpreters (FFmpeg, PyAV, SVG, Lottie, PNG sequence) consume the
same IR — new files, no core changes.

---

## 7. Determinism, Caching, Performance

### Determinism is a guarantee

- No `random`, no `time()`/`datetime.now()` in core paths.
- Registries iterate in registration order; plugin keys are stable.
- Easing/measure functions are pure; floats are rounded at exporter
  boundaries with documented precision.
- `LC_ALL`-independent parsing; no locale-aware formatting in core.
- Same version + same input files → **byte-identical output**.

This is why golden frames and timeline snapshots are checked into the test
suite.

### Caching (all at composition boundaries, never inside pure stages)

| Cache | Key | Wraps |
|---|---|---|
| `CompiledThemeCache` (LRU, 64) | (spec digest, catalog directories) | theme resolution |
| `TextMeasurer` measure LRU | (words, files, size, spacing, width) | measurement |
| `TimelineCache` (LRU, 64) | sha256 of `CaptionRequest.model_dump_json` | compilation |
| glyph cache (renderer-local) | (path, index, size) → PIL font | rasterization |

Note the theme cache keys on catalog *directories* (not manager identity), so
two managers over the same directories share entries; resolved themes are
shared and treated as read-only downstream.

### Performance strategy

- **Lazy loading:** fonts and theme files load on first use; nothing is
  scanned at import time.
- **Parallel rendering:** timeline sampling and rasterization are
  embarrassingly parallel per batch — `ProcessPoolExecutor` at the
  composition boundary.
- **Memory:** streams frames in chunks; never materializes hour-long videos
  in memory.
- **Numerics:** numpy-vectorized sampling for large timelines.

---

## 8. Testing & Benchmarks

- **Unit** — one subsystem per file; **389 tests**.
- **Timeline snapshot** — compile a request, dump `SubtitleTimeline` to JSON,
  compare against the checked-in snapshot under `tests/snapshots/timeline/`
  (regenerate with `MC_UPDATE_SNAPSHOTS=1` — rewrites are printed, never
  silent).
- **Animation snapshot** — sample curves at fixed t values, compare against
  `tests/snapshots/animation/`.
- **Golden frames** — render at fixed t on a pinned font, compare PNG bytes
  against `tests/snapshots/golden/`. Font pinning: the bundled
  `tests/fonts/Roboto-Regular.ttf` is referenced **by path**, so CI and
  laptops agree; the committed PNG is byte-stable for the generating
  Pillow/FreeType version.
- **Determinism** — compile the same request twice; assert byte equality
  (`Compiler` cache included).
- **Benchmarks** — `benchmarks/bench.py` times cold/warm compile, frame
  render, sequence render and both exporters over the pinned pipeline
  (`python benchmarks/bench.py --iterations 20`).

---

## 9. Installation & Imports

```bash
pip install -e ".[dev]"     # development
pip install motion-caption   # once published
```

Requires Python 3.12+. Optional extras: `ai` (OpenAI / Gemini providers),
`whisper` (WhisperX transcript import).

### Importing Top-Level API

```python
from motion_caption import (
    AssOptions,
    Canvas,
    CaptionRenderer,
    CaptionRequest,
    RenderOptions,
    Segment,
    SubtitleTimeline,
    Transcript,
    Word,
    WordTimestamp,
    build_ass,
    load_theme,
    resolve_theme,
    segment_transcript,
)

# Compiler / IR / AI / plugins live in their own modules
# (CaptionRequest / SubtitleTimeline are the same objects, re-exported
#  at the top level from motion_caption.ir)
from motion_caption.compiler import compile, Compiler
from motion_caption.exporters import EXPORTER_REGISTRY, AssExporter, JsonExporter
from motion_caption.ai import annotate, AI_REGISTRY, AIProvider
from motion_caption.plugins import load_plugins, PLUGIN_GROUPS
from motion_caption.ir import AIContribution, CaptionRequest, SubtitleTimeline
```

---

## 10. Usage Examples

### 10a. Compiler-first (recommended)

Compile one `CaptionRequest` into a `SubtitleTimeline`, then feed any
backend — rendering and both exporters share the same compiled artifact:

```python
from motion_caption import Canvas, CaptionRequest, Transcript, WordTimestamp
from motion_caption.compiler import compile
from motion_caption.exporters import EXPORTER_REGISTRY
from motion_caption.render import TimelineRenderer

# 1. One serializable request
request = CaptionRequest(
    transcript=Transcript(
        words=[
            WordTimestamp(text="Hello", start=0.0, end=0.8),
            WordTimestamp(text="motion", start=0.9, end=1.6),
            WordTimestamp(text="typography", start=1.7, end=2.5),
        ]
    ),
    theme="music_video",  # a ThemeSpec, a registry name, or None
)

# 2. Compile once
canvas = Canvas.from_standard("1080p")
timeline = compile(request)

# 3. Any backend consumes the same timeline
frame = TimelineRenderer().render_frame(timeline, t=1.2, canvas=canvas)
frame.save("frame_1.2s.png")

frames = TimelineRenderer().render_sequence(timeline, canvas, fps=30)

ass = EXPORTER_REGISTRY.get("ass").export(timeline).data
json_timeline = EXPORTER_REGISTRY.get("json").export(timeline).data
```

### 10b. Backward-compatible facade

The original segment/theme API still works; it compiles internally and
delegates to the same `TimelineRenderer`:

```python
from motion_caption import (
    Canvas,
    CaptionRenderer,
    RenderOptions,
    ResolutionContext,
    Segment,
    ThemeSpec,
    Word,
    resolve_theme,
)

canvas = Canvas.from_standard("1080p")
ctx = ResolutionContext(canvas=canvas.resolution)
theme = resolve_theme(ThemeSpec(name="demo"))

segments = [
    Segment(
        text="Hello motion typography",
        start=0.0,
        end=2.5,
        words=[
            Word(text="Hello", start=0.0, end=0.8),
            Word(text="motion", start=0.9, end=1.6),
            Word(text="typography", start=1.7, end=2.5),
        ],
    )
]

renderer = CaptionRenderer()
frame = renderer.render_frame(segments, theme, ctx, canvas, t=1.2)
frame.save("frame_1.2s.png")

frames = renderer.render_sequence(
    segments, theme, ctx, canvas, options=RenderOptions(fps=30)
)
```

### 10c. AI is optional — annotate, then compile

The compiler is fully deterministic with no model in the loop. An
`AIProvider` runs *outside* the compiler and writes precomputed annotations
onto the request:

```python
from motion_caption import Canvas, CaptionRequest, Transcript, WordTimestamp
from motion_caption.ai import AI_REGISTRY, annotate
from motion_caption.compiler import compile

request = CaptionRequest(
    transcript=Transcript(words=[WordTimestamp(text="hi", start=0.0, end=0.5)]),
    theme=None,               # let Gemini recommend one
)

annotated = annotate(request, AI_REGISTRY.get("gemini"))  # live call; reads GEMINI_API_KEY
timeline = compile(annotated)                             # compiler prefers llm_annotations
```

Set the key before running (nothing loads `.env` automatically):

```bash
echo 'GEMINI_API_KEY=your-key' > .env   # .env is gitignored
set -a; source .env; set +a
```

`GeminiProvider` defaults to `gemini-2.5-flash` (some keys carry no quota on
older models); override with `GeminiProvider(model=...)`. Without a provider,
rule-based segmentation and emphasis are the fallback. `annotate()` returns a
copy — the original request is untouched, and calling it twice with a
stochastic provider yields two independent annotations.

### 10d. Loading plugins

Nothing is scanned at import time; plugins load explicitly at startup:

```python
from motion_caption.plugins import load_plugins

load_plugins()                     # all eight entry-point groups
load_plugins(["exporters", "ai"])  # or a subset
```

---

## 11. Complete API Reference

### Canvas & Resolutions (`motion_caption.canvas`)
- `Canvas(width: int, height: int)`: Target resolution frame.
- `Canvas.from_standard(resolution: str)`: Factory for `"720p"`, `"1080p"`, `"2k"`, `"4k"`, `"portrait"` (1080x1920), `"shorts"`, `"square"`.
- `StandardResolution`: Enum of standard resolutions.
- `AspectRatio`: Enum (`LANDSCAPE`, `PORTRAIT`, `SQUARE`).

### Models (`motion_caption.models`)
- **Transcript & Words**:
  - `Transcript(language="en", words=[...])`: Semantic input.
  - `WordTimestamp(text: str, start: float, end: float, confidence: float)`: WhisperX-compatible raw token.
  - `Word(text: str, start: float, end: float, importance: float, emphasis: EmphasisMode)`: Enriched word.
  - `Segment(text: str, start: float, end: float, words=[...])`: Caption block.
  - `EmphasisMode`: Enum (`none`, `low`, `medium`, `high`, `karaoke`).
- **Units & Geometry**:
  - `Length(value, unit=Unit.PX)`: Resolution-independent length supporting `px`, `em`, `%`, `vw`, `vh`.
  - `Resolution(width: int, height: int)`: Pixel resolution.
  - `DesignSpace(reference: Resolution, policy: ScalePolicy)`: Authoring scale space.
  - `ResolutionContext(canvas: Resolution, design: DesignSpace, font_size: float)`: Context for resolving lengths.
  - `Point(x: float, y: float)`, `Size(width: float, height: float)`, `Box(left, top, right, bottom)`: 2D geometry primitives.
  - `Padding(left, top, right, bottom)`: Resolution-independent padding.
- **Color & Fills**:
  - `Color(r, g, b, a)`: RGBA color supporting hex strings (`"#FF0000"`), tuples, and CSS rgba.
  - `GradientFill(kind, stops, angle)`, `GradientStop(color, position)`, `FillSpec`.
- **Keyframes & Timelines**:
  - `PropertyKind`: Enum of animatable properties (`position`, `scale`, `rotation`, `opacity`, `blur`, `color`, etc.).
  - `Keyframe(time, value, ease)`: Single keyframe with easing.
  - `KeyframeTimeline(kind, keyframes)`: Ordered set of keyframes with interpolation.
  - `Region(position, scale, rotation, opacity, ...)`: Fully sampled snapshot at time `t`.
  - `RegionTimeline`: Composition of per-property tracks sampling to a `Region`.

### Segmentation (`motion_caption.segmentation`)
- `segment_transcript(transcript, config=None, strategy="sentence")`: Split transcript into segments.
- `Segmenter(config=None, strategy="sentence")`: Object facade for segmentation.
- `SegmentationConfig`: Tuning knobs (`max_words`, `max_duration`, `min_duration`, `target_words`, `pause_threshold`).
- Strategies (`SEGMENTATION_REGISTRY`): `"sentence"` (default grammar + pauses), `"pauses"` (silence-only), `"strict"` (hard caps).
- `reading_speed(block)`: Words per second over duration.

### Reading Analysis (`motion_caption.reading`)
- `analyze(transcript, config=None)`: Compute reading difficulty and pacing statistics (`ReadingStats`).
- `adjust_segments(segments, stats)`: Automatically tune durations based on reading density.
- `difficulty_of(text)`: Text complexity score.

### Emphasis (`motion_caption.emphasis`)
- `apply_emphasis(transcript, config=None)`: Assign emphasis modes to words based on importance scoring.
- `importance_to_mode(score)`: Convert 0..1 importance score to `EmphasisMode`.

### Themes (`motion_caption.themes`)
- `load_theme(name: str)`: Look up theme spec by name.
- `resolve_theme(spec, font_manager=None)`: Bind `ThemeSpec` to concrete fonts and compiled easings (`ResolvedTheme`).
- `builtin_themes()`: Dictionary of built-in theme specs (`"clean"`, `"music_video"`, `"cinematic"`, `"sport"`, `"news"`, `"default"`).
- `ThemeSpec`, `AnimationPersonality`, `EmphasisAppearance`, `ResolvedTheme`.

### Easing (`motion_caption.easing`)
- `compile_spec(spec: EasingSpec) -> EasingFunction`: Compile easing name/params into a callable `(float) -> float`.
- Built-in Easings (`easing_registry`): `"linear"`, `"step"`, `"cubic-bezier"`, `"spring"`, `"bounce"`, `"elastic"`, `"overshoot"`.

### Animations (`motion_caption.animations`)
- `build_word_items(segments, theme, config=None)`: Build per-word `WordItem` instances with canonical `RegionTimeline` keyframe tracks.
- `animate_word(word, theme, config, start, end)`: Build animated region for one word.
- `AnimationConfig(strategy="fade", in_window=0.2, out_window=0.15, params={})`: Tuning knobs.
- Templates (`ANIMATION_REGISTRY`): `"none"`, `"fade"`, `"slide"`, `"pop"`, `"scale"`, `"bounce"`, `"spring"`, `"elastic"`, `"overshoot"`, `"ripple"`, `"rotate"`, `"blur"`, `"glow"`, `"karaoke"`, `"pulse"`.

### Typography (`motion_caption.typography`)
- `TextStyle`: Full typography specification (`font`, `size`, `letter_spacing`, `word_spacing`, `line_height`, `fill`, `stroke`, `shadow`, `glow`, `background`, `opacity`, `blur`, `uppercase`, `align`).
- `TextMeasurer`: Measures text blocks and individual words using Pillow font metrics.
- `FontManager`, `FontStack`: System font discovery and stack resolution.

### Layout (`motion_caption.layout`)
- `lay_out(block, canvas, options, ctx)`: Position a measured block onto the canvas.
- `LayoutEngine`: Measure → wrap → position facade.
- `LayoutOptions(align=TextAlign.CENTER, max_width="85vw", margin=Padding(), vertical_bias=1.0)`: Layout tuning.
- `PlacedBlock`: Measured block positioned at absolute canvas coordinates.

### Placement (`motion_caption.placement`)
- `place(placed, canvas, config=None, faces=())`: Apply placement strategy and safe areas.
- `PlacementConfig(platform=None, safe_area=None, strategy="bottom", vertical_bias=1.0, horizontal_bias=0.5, face_margin=0.0)`: Placement tuning.
- Strategies (`PLACEMENT_REGISTRY`): `"bottom"`, `"top"`, `"center"`, `"face-aware"`.
- `platform_safe_area(name)`: Platform inset lookup (`"tiktok"`, `"instagram_reels"`, `"youtube_shorts"`, `"landscape"`, `"square"`).
- `avoid_faces(region, faces, canvas, margin=0.0)`: Face-avoidance repositioning.

### Renderer (`motion_caption.render`)
- `CaptionRenderer(measurer=None)`: Deterministic Pillow rasterizer.
- `CaptionRenderer.render_frame(segments, theme, ctx, canvas, t, options=None) -> Image.Image`
- `CaptionRenderer.render_sequence(segments, theme, ctx, canvas, options=None, start=None, end=None) -> list[Image.Image]`
- `RenderOptions(fps=30, clear_color=(0,0,0,0), layout=..., placement=..., animation=..., faces=...)`: Rasterizer tuning.
- `TimelineRenderer`: Dumb rasterizer that draws only from a compiled `SubtitleTimeline` — `render_frame(timeline, t, canvas)` / `render_sequence(timeline, canvas, fps=30)`, applying `timeline.scale` once. `CaptionRenderer` compiles a `CaptionRequest` internally and delegates to it.

### Exporters (`motion_caption.exporters`)
- `Exporter` (protocol) + `ExporterResult(data, media_type, extension)`: every backend consumes only `SubtitleTimeline`.
- `AssExporter` / `JsonExporter`: IR-based ASS and JSON backends (dispatch via `EXPORTER_REGISTRY`).
- `build_ass(segments, theme, ctx, canvas, options=None) -> str`: backward-compatible facade — compiles a `CaptionRequest` internally and delegates to `AssExporter`.
- `AssOptions(fps=30, layout=..., placement=..., animation=..., faces=..., style_name="Default")`: ASS exporter tuning (`layout`/`placement`/`animation`/`faces` configure the compile; `fps`/`style_name` tune the output).
- `EXPORTER_REGISTRY`: `Registry[Exporter]` dispatching by name (`"ass"`, `"json"`); the `motion_caption.exporters` entry-point group loads third-party backends.

### Compiler (`motion_caption.compiler`)
- `Compiler(font_manager=None, cache_size=64)`: Composition root. Owns the
  timeline cache (sha256 of `CaptionRequest.model_dump_json`) and the
  `CompiledThemeCache`; `compile(request) -> SubtitleTimeline`;
  `invalidate()` clears both.
- `compile(request)`: Compile through the process-wide shared `Compiler`.
- `default_compiler()`: The shared instance.
- `request_from_segments(segments, theme, ctx, canvas, layout=...,
  placement=..., animation=..., faces=...)`: Builds a `CaptionRequest` from
  the legacy segment/theme objects (used by `CaptionRenderer` and `build_ass`
  internally).
- `CompiledThemeCache(size=64)`: LRU of resolved themes keyed by (spec
  digest, catalog directories); themes are shared and treated as read-only.

### The IR (`motion_caption.ir`)
- `SubtitleTimeline(format_version, metadata, resolution, design, scale,
  styles, tracks)`: The canonical IR — the single source of truth for every
  backend. Helpers: `events`, `words`, `start`, `end`, `duration`,
  `events_at(t)`, `words_at(t)`, `style(name)`.
- `Track(name, speaker, events)`: One speaker/layer lane of `SubtitleEvent`s.
- `SubtitleEvent(start, end, text, style, region, words, speaker, layer)`: One
  caption on screen; `sample(t)` returns the per-word `Region`s.
- `WordEvent(text, start, end, importance, emphasis, box, typography,
  animation)`: One word with its measured `box`, `ResolvedTypography`, and
  `AnimationTrack`; `region_at(t)` samples its motion.
- `StyleTrack(name, typography)` / `PlacementRegion(box, anchor, speaker,
  layer)` / `AnimationTrack(tracks, phases)` / `KeyframeTrack(kind,
  timeline)` / `AIContribution(importance, emphasis, splits, theme, emotion)`.

### AI seam (`motion_caption.ai`)
- `AIProvider` (protocol): `annotate(request) -> AIContribution`. Providers
  run **outside** the compiler; core never imports an SDK.
- `annotate(request, provider) -> CaptionRequest`: Returns a copy with
  `llm_annotations` attached (the original is untouched — determinism is
  preserved). **Makes a live provider call.**
- `AI_REGISTRY`: Built-in providers (`"openai"`, `"gemini"`) plus any from
  the `motion_caption.ai` entry-point group.
- `OpenAIProvider(api_key=None)` / `GeminiProvider(api_key=None, model="gemini-2.5-flash")`:
  Reference implementations with **lazy SDK imports** (install the `ai`
  extra); API keys fall back to `OPENAI_API_KEY` / `GEMINI_API_KEY`. Their
  JSON output feeds `AIContribution`.

### Plugins (`motion_caption.plugins`)
- `PLUGIN_GROUPS`: Maps the eight entry-point groups to their registries
  (`themes`, `animations`, `easings`, `exporters`, `placements`,
  `segmentation`, `emphasis`, `ai`).
- `load_plugins(groups=None)`: Explicit, opt-in loading of registered
  entry-point plugins (nothing is scanned at import time). Call it once at
  startup if you ship plugins.

---

## 12. Design Principles

1. **Semantics are separate from rendering.** One graph, many outputs (ASS,
   PNG, JSON, FFmpeg).
2. **Everything is keyframes.** Every subtitle becomes a small timeline of
   keyframed properties interpolated by easing functions — the single source
   of truth that makes determinism and multiple exporters free.
3. **Purity before speed.** Subsystems are pure functions over models.
   Caching and parallelism live at composition boundaries, never in core.
4. **Open for extension, closed for modification.** New themes, animations,
   easings, exporters, placement strategies and AI providers register
   themselves. Core code never knows a concrete plugin.
5. **Resolution independence is a first-class unit system.** All lengths are
   typed (`px`, `em`, `%`, `vw`, `vh`) and resolved against a design space.
6. **Determinism is a guarantee.** No RNG, no wall-clock, no iteration-order
   dependence. Identical input → identical output bytes.
7. **AI is optional.** No LLM required; AI output is precomputed input.
   Everything visual remains deterministic.

## 13. Trade-off Log

| Decision | Why | Cost |
|---|---|---|
| Keyframes as canonical truth | single source → determinism, all exporters free | exporters must interpret curves (e.g. ASS `\t` baking) |
| Pydantic everywhere | strict validation, serialization for editors & AI | object overhead (mitigated by caching) |
| IR in resolved design-space px | compile once, export everywhere; canvas-independent caches | exporters multiply by `scale` |
| CSS-like `Length` units | resolution independence without rebuilding styles | resolver complexity |
| fonttools for coverage | real per-char fallback, accurate weight matching | a small pure-Python dependency |
| Greedy (not Knuth-Plass) wrapping | deterministic, fast, predictable | occasionally suboptimal breaks (segmentation is the real wrap control) |
| Plugin registry (not ABC discovery) | explicit, debuggable, entry-point compatible | users must know plugin names |
| Pure pipeline stages | easy to test, cache, parallelize | boilerplate at composition boundary |
| AI output is precomputed input | deterministic pipeline; no SDK in core | AI must run before compile |
| `CaptionRenderer` is a facade | zero breakage; one rasterizer path | one extra indirection |
