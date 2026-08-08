# MotionCaption — Complete Developer Guide & API Reference

**MotionCaption** is a deterministic, plugin-based motion typography and animated subtitle engine for Python. It transforms word-timed transcripts (such as from WhisperX) into professional, highly styled caption animations rendered as RGBA image sequences via Pillow or exported directly to Advanced SubStation Alpha (`.ass`) files.

---

## 1. How It Works (The Compiler Pipeline)

MotionCaption behaves like a **compiler**: one serializable input, a
canonical intermediate representation, and interchangeable backends.

1. **`CaptionRequest` (input)**: Everything the pipeline needs — word-timed
   transcript, theme (a `ThemeSpec` or registry name), resolution/design,
   faces, safe area, platform, speaker tracks, and optional precomputed AI
   annotations (`llm_annotations`). One object, fully serializable.
2. **Compiler stages (pure, replaceable)**: The `Compiler` runs segmentation
   (grammar/rhythm-aware `Segment` blocks), emphasis (importance →
   `EmphasisMode`), reading-paced durations, theme resolution (fonts + easing
   identities bound), typography resolution (every `Length` → design px),
   layout (measure + wrap + align), placement (safe areas, face avoidance,
   speaker bias), and animation (per-word `AnimationTrack` keyframes).
3. **`SubtitleTimeline` (canonical IR)**: The resolved, deterministic output
   of the compiler — measured word boxes, resolved typography, keyframed
   motion, and final placement regions, all in design-space pixels with a
   single `scale` factor. This is the **single source of truth**.
4. **Backends consume the IR**: `TimelineRenderer` samples it into RGBA
   frames (`CaptionRenderer` is a backward-compatible facade that compiles
   internally and delegates), and exporters (`AssExporter`, `JsonExporter`)
   interpret it into `.ass` / JSON. No backend measures, picks fonts,
   lays out, or animates — everything is already resolved.

The legacy object pipeline (transcript → segments → words → keyframed
regions) still exists underneath — the compiler's stages are exactly that
chain, unified behind the IR.

---

## 2. Installation & Imports

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
from motion_caption.compiler import compile, Compiler
from motion_caption.exporters import EXPORTER_REGISTRY, AssExporter, JsonExporter
from motion_caption.ai import annotate, AI_REGISTRY
from motion_caption.plugins import load_plugins
```

---

## 3. Usage Example

### 3a. Compiler-first (recommended)

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

### 3b. Backward-compatible facade

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

---

## 4. Complete API Reference

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
- `builtin_themes()`: Dictionary of built-in theme specs (`"clean"`, `"music_video"`, `"cinematic"`, `"sport"`, `"news"`).
- `ThemeSpec`, `AnimationPersonality`, `EmphasisAppearance`, `ResolvedTheme`.

### Easing (`motion_caption.easing`)
- `compile_spec(spec: EasingSpec) -> EasingFunction`: Compile easing name/params into a callable `(float) -> float`.
- Built-in Easings (`EASING_REGISTRY`): `"linear"`, `"ease-in"`, `"ease-out"`, `"ease-in-out"`, `"spring"`, `"bounce"`, `"elastic"`, `"overshoot"`, etc.

### Animations (`motion_caption.animations`)
- `build_word_items(segments, theme, config=None)`: Build per-word `WordItem` instances with canonical `RegionTimeline` keyframe tracks.
- `animate_word(word, theme, config, start, end)`: Build animated region for one word.
- `AnimationConfig(strategy="fade", in_window=0.2, out_window=0.15, params={})`: Tuning knobs.
- Templates (`ANIMATION_REGISTRY`): `"none"`, `"fade"`, `"slide"`, `"pop"`, `"scale"`, `"bounce"`, `"spring"`, `"elastic"`, `"overshoot"`, `"ripple"`, `"rotate"`, `"blur"`, `"glow"`, `"karaoke"`, `"pulse"`.

### Typography (`motion_caption.typography`)
- `TextStyle`: Full typography specification (`font`, `size`, `letter_spacing`, `word_spacing`, `line_height`, `fill`, `stroke`, `shadow`, `glow`, `background`, `opacity`, `blur`, `uppercase`, `align`).
- `TextMeasurer`: Measures text blocks and individual words using Pillow font metrics.
- `FontManager`, `FontStack`, `FontFile`: System font discovery and stack resolution.

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
- `TimelineRenderer`: Dumb rasterizer that draws only from a compiled `SubtitleTimeline` — `render_frame(timeline, t, canvas)` / `render_sequence(...)`, applying `timeline.scale` once. `CaptionRenderer` compiles a `CaptionRequest` internally and delegates to it.

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
  timeline)`.

### AI seam (`motion_caption.ai`)
- `AIProvider` (protocol): `annotate(request) -> AIContribution`. Providers
  run **outside** the compiler; core never imports an SDK.
- `annotate(request, provider) -> CaptionRequest`: Returns a copy with
  `llm_annotations` attached (the original is untouched — determinism is
  preserved).
- `AI_REGISTRY`: Built-in providers (`"openai"`, `"gemini"`) plus any from
  the `motion_caption.ai` entry-point group.
- `OpenAIProvider(api_key=None)` / `GeminiProvider(api_key=None)`: Reference
  implementations with **lazy SDK imports** (install the `ai` extra); API
  keys fall back to `OPENAI_API_KEY` / `GEMINI_API_KEY`. Their JSON output
  feeds `AIContribution(importance, emphasis, splits, theme, emotion)`.

### Plugins (`motion_caption.plugins`)
- `PLUGIN_GROUPS`: Maps the eight entry-point groups to their registries
  (`themes`, `animations`, `easings`, `exporters`, `placements`,
  `segmentation`, `emphasis`, `ai`).
- `load_plugins(groups=None)`: Explicit, opt-in loading of registered
  entry-point plugins (nothing is scanned at import time). Call it once at
  startup if you ship plugins.
