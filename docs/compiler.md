# MotionCaption Compiler Architecture

> Status: **implemented** (through Phase 6). This document is both the design
> contract and the implementation reference; it supersedes the forward
> references in `architecture.md`. Existing public APIs remain unchanged;
> everything below now exists in the codebase.

MotionCaption is a **compiler**, not a subtitle renderer. The analogy is
deliberate and runs through every design decision:

| Concept | MotionCaption |
|---|---|
| Source program | `CaptionRequest` |
| Lexer / parser | segmentation |
| Semantic analysis | emphasis + reading |
| Frontend passes | theme resolution → typography → layout → placement |
| Canonical IR | `SubtitleTimeline` |
| Backends | exporters (ASS, JSON, FFmpeg, PNG, …) |

`SubtitleTimeline` is the single source of truth. Every subsystem reads the
request and writes the timeline; every exporter reads the timeline and writes
bytes. Nothing else in the pipeline is allowed to reach I/O.

---

## 1. Review of the current architecture

### 1.1 What is already strong (and stays)

- **Keyframes as canonical truth.** `RegionTimeline` → per-`PropertyKind`
  `KeyframeTimeline` → deterministic `sample(t) -> Region` is exactly the
  right animation substrate. It is reused, not replaced.
- **Typed, resolution-independent lengths.** `Length` (`px`/`em`/`%/`vw`/`vh`)
  + `DesignSpace`/`ScalePolicy`/`ResolutionContext` give us the "same style,
  every resolution" property for free.
- **Clean domain layer.** `models/` has zero dependencies on the rest of the
  package.
- **Plugin seams per subsystem.** `registry.py` (thread-safe, aliases,
  entry-point loading) already backs easing, animation, theme, placement,
  exporter, segmentation and emphasis registries. Decentralized by design.
- **Determinism discipline.** No RNG / wall-clock / locale formatting in core;
  pure easing and measurement. This is what makes golden tests possible.
- **Test culture.** One subsystem per file; 388 passing tests today (plus
  golden frames, timeline/animation snapshots and a benchmark script — §10).

### 1.2 Weaknesses identified (all resolved)

> Every item below was fixed in Phases 1–5; the fixes are recorded next to
> each entry. This section is kept as the rationale for why the architecture
> looks the way it does.

1. **No canonical IR; exporters re-run the pipeline.** `build_ass` measures,
   wraps, lays out, places and animates *itself* (exporters/ass.py:91–107),
   duplicating `CaptionRenderer._place_segment` (render/engine.py:63–80). The
   "one graph, many outputs" principle is violated: two backends already
   re-derive the same graph independently, and a third (JSON) would re-derive
   it again. Fix: compile once into `SubtitleTimeline`; backends consume.
2. **No unified request object.** Public APIs accept ad-hoc tuples
   (`segments`, `theme`, `ctx`, `canvas`, `options`). There is nowhere to put
   metadata, faces, platform, speaker tracks, or AI annotations — so those
   concepts are silently absent from the pipeline today.
3. **The renderer is not dumb.** `CaptionRenderer` measures, picks fonts,
   computes layout/placement and selects animations internally. That couples
   the rasterizer to typography, fonts, layout and themes — the exact
   coupling the goal forbids. Fix: `ResolvedTypography` + `SubtitleTimeline`
   carry everything; a new `TimelineRenderer` only draws.
4. **Theme resolution is not cached.** `resolve_theme` calls
   `manager.resolve_stack` (a full font-directory scan on first use) on every
   call. No `CompiledTheme` cache, no compile cache.
5. **Typography resolution is scattered.** The renderer resolves
   shadow/stroke/glow/background lengths inline (render/engine.py:108–143,
   225–252). Resolved styles should be a first-class artifact
   (`ResolvedTypography`), produced once by a dedicated stage.
6. **Placement has no speaker concept.** `Face`, `SafeArea` exist, but
   multi-speaker positioning is absent. `CaptionRequest.speaker_tracks` closes
   this.
7. **`PropertyKind` is a closed enum.** Plugin-defined animatable properties
   need the enum + interpolation typing. Kept for compatibility; the
   `KeyframeTrack` wrapper below is the extension seam (a property registry is
   deferred).
8. **No exporter contract.** `EXPORTER_REGISTRY` maps name → bare callable.
   No `Exporter` protocol, no result type, no extension dispatch.
9. **No AI seam in the code.** Only documented. No `AIProvider` protocol, no
   `AIContribution` shape, no place for annotations to enter the pipeline.
10. **No golden/snapshot/benchmark harness.** Determinism is asserted by unit
    tests, not by byte-compare frames or timeline snapshots.
11. **Docs are stale.** `README.md` still lists most subsystems as "up next".
    *Resolved (Phase 6):* `README.md` rewritten around the compiler pipeline;
    `GUIDE.md` documents the compiler/IR/AI/plugin surfaces; this document is
    the compiler contract.

---

## 2. Design: `CaptionRequest` (input)

One serializable object is the input to every public API.

```python
class CaptionRequest(BaseModel):
    metadata: dict[str, Any] = {}          # title, episode, language, job id, ...
    transcript: Transcript
    faces: list[Face] = []
    safe_area: SafeArea | None = None
    platform: str | None = None            # "tiktok", "youtube_shorts", ...
    theme: ThemeSpec | str | None = None   # spec, or name for the registry
    llm_annotations: AIContribution | None = None   # optional, precomputed
    speaker_tracks: list[SpeakerTrack] = []
    resolution: Resolution | StandardResolution | str | None = None
    design: DesignSpace | None = None      # default 1920x1080 COVER
    options: CompileOptions | None = None  # segmentation/animation/layout/placement/reading
    future_extensions: dict[str, Any] = {}
```

Decisions:

- **`theme` accepts a name or a spec.** A `ThemeSpec` is data (JSON); a theme
  *name* is data too. Because the compiler resolves it, a request can carry a
  name and be serialized — which is exactly what an AI theme recommendation or
  an editor round-trip needs.
- **`llm_annotations` is an *input*, not a live call.** AI runs *outside* the
  deterministic compiler; its output is precomputed data attached to the
  request. This keeps the pipeline pure, replayable, and SDK-free.
- **`resolution` is optional with a default.** The compiler produces a
  timeline in *design-space pixels* (see §4), so the request can name a canvas
  (for layout sanity) while the timeline stays resolution-independent and can
  be re-exported at any size.
- **`future_extensions` is a free-form dict.** Unplanned inputs (audio
  features, brand colors, per-platform overrides) enter without a breaking
  change. Forward compatibility is a stated goal.

### `AIContribution` (the only AI shape)

```python
class AIContribution(BaseModel):
    importance: dict[int, float] | None = None      # word index -> 0..1
    emphasis: dict[int, EmphasisMode] | None = None
    splits: list[list[int]] | None = None           # word-index groups
    theme: str | None = None                        # recommended theme name
    emotion: str | None = None
```

The `AIProvider` protocol (deferred, §9) returns this. Providers are never
imported by core.

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

## 3. Design: the IR — `SubtitleTimeline`

The IR is pure data. It imports only `models/` primitives (`Point`, `Box`,
`Color`, `Keyframe`, `KeyframeTimeline`, `PropertyKind`, `Region`) and
`typing` — **not** themes, fonts, layout or placement code. That makes it
serializable to JSON byte-for-byte and guarantees determinism: identical
request → identical timeline.

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

### 3.1 `ResolvedTypography`

A `TextStyle` with every `Length` resolved to a float in design-space pixels,
and fonts resolved to concrete faces. This is the object the renderer draws
from — the renderer never resolves a length again.

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

Why floats and not `Length`? Because an exporter or rasterizer must never
re-resolve typography. `Length` resolution requires a `ResolutionContext`;
once we resolve at the typography stage, everything downstream is pure math.

### 3.2 `KeyframeTrack`, `AnimationTrack`, `Region`

```python
class KeyframeTrack(BaseModel):
    kind: PropertyKind
    timeline: KeyframeTimeline        # reuse: ordered keyframes + sample()

class AnimationTrack(BaseModel):
    tracks: dict[PropertyKind, KeyframeTrack]
    phases: dict[str, tuple[float, float]] = {}   # "in"/"out"/"idle" spans
    def sample(self, t: float) -> Region: ...     # composition -> Region
```

`Region` is the existing sampled snapshot from `models.keyframe`. Decision:
**do not invent a new animation model.** `RegionTimeline` already composes
property tracks and samples deterministically; `AnimationTrack` wraps the same
idea under the compiler vocabulary and adds phase metadata (which exporters
can use for `\t` segmentation or karaoke fills). The closed `PropertyKind`
enum stays — a property registry is a documented extension point, not a v1
requirement.

### 3.3 `PlacementRegion` and `Track`

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

### 3.4 Why the IR stores *resolved design-space* pixels

The timeline is compiled at the request's `design.reference` resolution
(1920×1080 by default). `timeline.scale` maps design px → output px for the
requested canvas. Exporters apply `scale` once. Consequences:

- **Compile once, export everywhere.** A single `SubtitleTimeline` renders to
  720p, 4K and portrait by multiplying by `scale` — no re-measure, no rebuild.
- **Deterministic by construction.** No target-dependent state is captured in
  the IR.
- **Caches are small and canvas-independent.** Measurement/layout/animation
  caches are keyed on design px, so one 1080p compile feeds all outputs.

The renderer and ASS exporter are the only consumers that multiply by
`scale`, exactly like a codegen backend materializing for a target ISA.

---

## 4. Design: the compiler pipeline

Every stage is a pure function `CompileContext -> CompileContext`. Stages are
in module `motion_caption/compiler/` and are individually replaceable.

```
CaptionRequest
   │
   ▼ [0] normalize        → defaults: canvas, design, options, theme name lookup
   ▼ [1] segment          → Transcript → list[Segment]      (SEGMENTATION_REGISTRY)
   ▼ [2] emphasize        → per-word importance + EmphasisMode (EMPHASIS_REGISTRY)
   ▼ [3] pace             → extend ends for reading speed    (reading engine)
   ▼ [4] resolve theme    → ResolvedTheme (CompiledTheme cache; fonts resolved)
   ▼ [5] resolve typography → base ResolvedTypography + per-emphasis deltas
   ▼ [6] measure + layout → MeasuredBlock → PlacedBlock per segment (speaker-aware)
   ▼ [7] animate          → per-word AnimationTrack           (ANIMATION_REGISTRY)
   ▼ [8] place            → safe area + face-aware + speaker bias → PlacementRegion
   ▼ [9] assemble         → SubtitleTimeline (IR)             (compile cache)
   ▼
SubtitleTimeline
   │
   ├─ [10] render  → TimelineRenderer draws only (fonts already chosen)
   └─ [10] export  → ASS / JSON / FFmpeg / PNG  (EXPORTER_REGISTRY)
```

Decisions:

- **Typography is separate from layout** (stages 5 vs 6). Layout performs
  measurement, wrapping, alignment, positioning — nothing else. Typography
  answers "what does the text look like"; layout answers "where do the glyphs
  go". They are coupled only through `ResolvedTypography`.
- **Placement is last and only about position.** Safe areas, face avoidance,
  speaker stacking, portrait/landscape. It never touches style or motion.
- **Theme resolution happens before typography, but the renderer never sees a
  theme.** The renderer consumes `ResolvedTypography` + `AnimationTrack`.
- **`CompileContext` is the stage bus.** It carries the request, enriched
  segments, `ResolvedTheme`, resolved typography, placed blocks, word items,
  and the final timeline. Stages only read/write fields they own.

### 4.1 Caching (all at composition boundaries)

| Cache | Key | Stage |
|---|---|---|
| `CompiledThemeCache` (LRU, size 64) | (spec digest, catalog directories) | 4 |
| measure (existing `TextMeasurer` LRU) | (words, files, size, spacing, width) | 6 |
| `TimelineCache` (LRU, size 64) | sha256 of `CaptionRequest.model_dump_json` | 9 |
| glyph cache (renderer-local) | (path, index, size) → PIL font | 10 |

All four exist today. Caches are never inside a pure stage; they wrap stage
invocation in the `Compiler` (and the renderer). Determinism is untouched —
caches are exact-key LRUs. Note the theme cache keys on catalog
*directories* (not manager identity), so two managers over the same
directories share entries; resolved themes are shared and treated as
read-only by downstream stages.

---

## 5. Design: exporters

### 5.1 The contract

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

Implementations may accept extra keyword options beyond ``timeline`` (e.g.
``AssExporter.export(timeline, *, fps=30, style_name="Default")``,
``JsonExporter.export(timeline, *, indent=2)``) — a call with only
``timeline`` must always succeed. Exactly this protocol ships in
``exporters/protocol.py``.

Every exporter consumes **only** `SubtitleTimeline`. No exporter measures,
picks fonts, lays out, or animates. The registry dispatches by name
(no switch statements); entry-point group `motion_caption.exporters` loads
third-party backends.

### 5.2 Backends

- **ASS** — re-expressed as a consumer of the IR. It still bakes `\t`
  override segments by sampling `AnimationTrack` (the correct "interpreter"
  behavior), but reads positions/colors/fonts from `WordEvent`/`ResolvedTypography`.
- **JSON timeline** — free: the IR is already pydantic; `model_dump_json`
  with rounding at documented precision.
- **FFmpeg / PyAV / PNG sequence / SVG / Lottie** — same IR, new interpreters.
  No core changes.

`build_ass(...)` keeps its signature; it now compiles internally and delegates
to the ASS backend (backward compatible).

---

## 6. Design: renderer

`TimelineRenderer` is dumb: given `SubtitleTimeline`, `t`, and a target
canvas, it (a) finds overlapping `SubtitleEvent`s, (b) samples each
`AnimationTrack` → `Region`, (c) composites glyphs with `ResolvedTypography`
at `region.position + word.box * scale`. It does not measure, choose fonts,
compute layout, or know themes exist.

`CaptionRenderer` remains public and unchanged in signature: its methods
compile a `CaptionRequest` internally and delegate to `TimelineRenderer`.
Nobody's existing code breaks; the *implementation* moves behind the compiler.

---

## 7. Design: plugin system

Stays with `Registry` (already thread-safe, alias-aware, entry-point-ready),
but presented through a single aggregation module `motion_caption/plugins.py`
so there is exactly one place that wires entry-point groups:

| Entry-point group | Registers |
|---|---|
| `motion_caption.themes` | ThemeSpec factory / ThemeSpec |
| `motion_caption.animations` | Animation template |
| `motion_caption.easings` | Easing factory |
| `motion_caption.exporters` | Exporter class |
| `motion_caption.placements` | Placement strategy |
| `motion_caption.segmentation` | Segmentation strategy |
| `motion_caption.emphasis` | Emphasis scorer |
| `motion_caption.ai` | AIProvider class |

No switch statements anywhere: dispatch is `registry.get(key)(...)`. Plugin
surfaces are narrow protocols (one callable / one class each).

---

## 8. Backward compatibility contract

- Every name in `motion_caption/__init__.py` stays and keeps its semantics.
- `CaptionRenderer.render_frame` / `render_sequence` keep their signatures.
- `build_ass`, `segment_transcript`, `apply_emphasis`, `resolve_theme`,
  `place`, `lay_out`, `compile_spec` — unchanged.
- All additions are new modules: `motion_caption/ir/`,
  `motion_caption/compiler/`, `motion_caption/render/timeline.py`,
  `motion_caption/plugins.py`, plus additive exports.
- `models/` remains dependency-free.

---

## 9. AI seam (implemented)

```python
class AIProvider(Protocol):
    name: str
    def annotate(self, request: CaptionRequest) -> AIContribution: ...
```

Implemented in `motion_caption/ai/`: `AIProvider`, `AI_REGISTRY`, the
`annotate(request, provider)` helper (returns a copy — the input request is
never mutated, preserving determinism), and reference `OpenAIProvider` /
`GeminiProvider` with lazy SDK imports (the `ai` extra installs the SDKs;
core stays dependency-free). Deterministic fallback = rule-based scorer +
segmentation strategies. A provider configured at the composition root
writes `llm_annotations` onto the request; the compiler prefers them when
present. Providers are never imported by core; the `motion_caption.ai`
entry-point group is the only wiring.

---

## 10. Testing strategy (implemented)

- **Unit** — one subsystem per file; 388 tests.
- **Timeline snapshot** — compile a request, dump `SubtitleTimeline` to JSON,
  compare against the checked-in snapshot under `tests/snapshots/timeline/`
  (regenerate with `MC_UPDATE_SNAPSHOTS=1`).
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
  render, sequence render and both exporters over the pinned pipeline.

---

## 11. Implementation roadmap (one subsystem at a time)

1. ✅ **IR + request** — `ir/` package, `ResolvedTypography`, `SubtitleTimeline`,
   `CaptionRequest` (+ tests, exports).
2. ✅ **Compiler** — `compiler/` stages + `Compiler`/`compile()` (+ tests,
   determinism + cache).
3. ✅ **Exporters** — `Exporter` protocol, ASS refactor onto IR, JSON exporter
   (+ tests, snapshots).
4. ✅ **Dumb renderer** — `TimelineRenderer`, `CaptionRenderer` facade, golden
   frames.
5. ✅ **Caching layer** — `CompiledThemeCache`, `TimelineCache`, glyph cache.
6. ✅ **Plugin aggregation** — `plugins.py`, entry-point loading.
7. ✅ **AI seam** — `AIProvider` protocol + reference providers + registry.
8. ✅ **Docs + benchmarks** — README/GUIDE refresh (Phase 6),
   `benchmarks/bench.py`. (`docs/ir.md` and `docs/plugins.md` remain folded
   into `compiler.md` §3/§7 rather than separate files — recorded deviation.)

---

## 12. Trade-off log

| Decision | Why | Cost |
|---|---|---|
| IR in resolved design-space px | compile once, export everywhere; canvas-independent caches | exporters multiply by `scale` |
| `RegionTimeline` reused as `AnimationTrack` core | no new animation model; existing, tested sampling | phase metadata is additive |
| Typography resolved to floats in IR | renderers/exporters never resolve lengths | resolution happens once, earlier |
| AI output is precomputed input | deterministic pipeline; no SDK in core | AI must run before compile |
| `CaptionRenderer` is a facade | zero breakage; one rasterizer path | one extra indirection |
| Registry (not ABC) dispatch | explicit, entry-point compatible, already shipped | users must know plugin names |
| IR pure data, imports only `models/` | JSON-serializable, deterministic, cacheable | converters needed at the boundary |

---

*This document is the contract for the compiler subsystem. Deviations must be
recorded here before code is merged.*
