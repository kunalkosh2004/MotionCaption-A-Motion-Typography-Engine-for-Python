# MotionCaption — Complete Developer Guide & API Reference

**MotionCaption** is a deterministic, plugin-based motion typography and animated subtitle engine for Python. It transforms word-timed transcripts (such as from WhisperX) into professional, highly styled caption animations rendered as RGBA image sequences via Pillow or exported directly to Advanced SubStation Alpha (`.ass`) files.

---

## 1. How It Works (The Pipeline)

MotionCaption follows a strict, stateless unidirectional rendering pipeline:

1. **Transcript Input**: Raw word-timed tokens (`WordTimestamp`) with `start`, `end`, and `text`.
2. **Segmentation (`segmentation`)**: Chunks word timestamps into grammatical, rhythm-aware caption blocks (`Segment`) constrained by max word counts and durations.
3. **Emphasis (`emphasis`)**: Analyzes word importance (using part-of-speech heuristics and reading speed) to assign emphasis modes (`NONE`, `LOW`, `MEDIUM`, `HIGH`, `KARAOKE`).
4. **Themes (`themes`)**: Supplies typographic personalities (font stacks, base styles, glow/shadow/stroke), emphasis appearances, and easing identities. `resolve_theme()` binds spec to fonts.
5. **Animation & Keyframes (`animations`, `easing`, `models.keyframe`)**: Maps animation templates (e.g., `fade`, `pop`, `karaoke`, `spring`) to canonical per-property keyframe timelines (`RegionTimeline`).
6. **Typography & Measurement (`typography`)**: Measures glyph dimensions and bounds using Pillow and font managers.
7. **Layout & Placement (`layout`, `placement`)**: Positions measured blocks on the output canvas adhering to text alignments, safe areas (TikTok, Reels, Shorts), and facial-avoidance zones.
8. **Rasterization / Export (`render`, `exporters`)**: Samples canonical timelines at time `t` to composite RGBA frames (`CaptionRenderer`) or compiles subtitle events (`build_ass`).

---

## 2. Installation & Imports

### Importing Top-Level API
```python
from motion_caption import (
    Canvas,
    CaptionRenderer,
    RenderOptions,
    Segment,
    Transcript,
    Word,
    WordTimestamp,
    segment_transcript,
    resolve_theme,
    load_theme,
    build_ass,
    AssOptions,
)
```

---

## 3. Usage Example

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

# 1. Define output canvas & context
canvas = Canvas.from_standard("1080p")
ctx = ResolutionContext(canvas=canvas.resolution)

# 2. Load or build a theme
theme = resolve_theme(ThemeSpec(name="demo"))

# 3. Create caption segments with word timestamps
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

# 4. Render a single frame at t = 1.2s
renderer = CaptionRenderer()
frame = renderer.render_frame(segments, theme, ctx, canvas, t=1.2)
frame.save("frame_1.2s.png")

# Or render an entire sequence of frames at 30 fps
frames = renderer.render_sequence(
    segments,
    theme,
    ctx,
    canvas,
    options=RenderOptions(fps=30),
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
