"""CaptionRenderer facade: compile a CaptionRequest, delegate to TimelineRenderer.

The rasterizer never measures text, chooses fonts, computes layout or selects
animations. ``CaptionRenderer`` keeps its public API (``render_frame`` /
``render_sequence``) and compiles the caller's segments into a
``SubtitleTimeline``, which ``TimelineRenderer`` (``render/timeline.py``)
simply draws.

Fidelity notes (vs. the pre-compiler renderer):

- The caller's segments are rebuilt as a ``Transcript`` and passed to the
  compiler with ``llm_annotations.splits`` so the original word grouping is
  preserved. The first word's start and the last word's end are clamped to the
  segment window, so a caption whose on-screen span extends beyond its spoken
  words (e.g. reading-paced segments) keeps that window.
- Measurement, layout and placement now run once in the compiler at
  design-space resolution; ``timeline.scale`` maps onto the output canvas. For
  the standard setup (``ctx = ResolutionContext(canvas=...)`` with the default
  design space) output is identical to the previous implementation.

Two intentional behavioral changes vs. the pre-compiler renderer:

- Words using the ``none``/``static`` animation strategy are only drawn while
  their event is on screen (the old renderer drew them at every time ``t``).
- The theme's base glow (``TextStyle.glow``) is now rendered; the old
  rasterizer only drew per-emphasis glows. The dumb renderer draws exactly
  what ``ResolvedTypography`` says.
"""

from __future__ import annotations

from collections.abc import Sequence

from PIL import Image
from pydantic import BaseModel, Field

from motion_caption.animations import AnimationConfig
from motion_caption.canvas import Canvas
from motion_caption.compiler.engine import Compiler
from motion_caption.ir.request import AIContribution, CaptionRequest, CompileOptions
from motion_caption.ir.timeline import SubtitleTimeline
from motion_caption.layout import LayoutOptions
from motion_caption.models.transcript import EmphasisMode, Segment, Transcript, WordTimestamp
from motion_caption.models.units import ResolutionContext
from motion_caption.placement import Face, PlacementConfig
from motion_caption.render.timeline import TimelineRenderer
from motion_caption.themes.spec import ResolvedTheme
from motion_caption.typography.measure import TextMeasurer


class RenderOptions(BaseModel):
    """Tuning knobs for rasterization."""

    fps: int = Field(default=30, gt=0)
    clear_color: tuple[int, int, int, int] = (0, 0, 0, 0)
    layout: LayoutOptions = Field(default_factory=LayoutOptions)
    placement: PlacementConfig = Field(default_factory=PlacementConfig)
    animation: AnimationConfig = Field(default_factory=AnimationConfig)
    faces: list[Face] = Field(default_factory=list)


class CaptionRenderer:
    """Thin facade: compiles segments + theme into a timeline and draws it."""

    def __init__(self, measurer: TextMeasurer | None = None) -> None:
        self.measurer = measurer or TextMeasurer()
        self._compiler = Compiler(font_manager=self.measurer.fonts)
        self._drawer = TimelineRenderer()

    def _compile(
        self,
        segments: Sequence[Segment],
        theme: ResolvedTheme,
        ctx: ResolutionContext,
        canvas: Canvas,
        options: RenderOptions,
    ) -> SubtitleTimeline:
        transcript_words: list[WordTimestamp] = []
        splits: list[list[int]] = []
        importance: dict[int, float] = {}
        emphasis: dict[int, EmphasisMode] = {}
        index = 0
        for segment in segments:
            if not segment.words:
                continue
            start_index = index
            for offset, word in enumerate(segment.words):
                word_start = min(word.start, segment.start) if offset == 0 else word.start
                word_end = (
                    max(word.end, segment.end) if offset == len(segment.words) - 1 else word.end
                )
                transcript_words.append(
                    WordTimestamp(text=word.text, start=word_start, end=word_end)
                )
                importance[index] = word.importance
                emphasis[index] = word.emphasis
                index += 1
            splits.append(list(range(start_index, index)))
        request = CaptionRequest(
            transcript=Transcript(language="en", words=transcript_words),
            faces=list(options.faces),
            theme=theme.spec,
            llm_annotations=AIContribution(
                splits=splits,
                importance=importance,
                emphasis=emphasis,
            ),
            resolution=canvas.resolution,
            design=ctx.design,
            options=CompileOptions(
                strategy="strict",
                reading=False,
                animation=options.animation,
                layout=options.layout,
                placement=options.placement,
            ),
        )
        return self._compiler.compile(request)

    def render_frame(
        self,
        segments: Sequence[Segment],
        theme: ResolvedTheme,
        ctx: ResolutionContext,
        canvas: Canvas,
        t: float,
        *,
        options: RenderOptions | None = None,
    ) -> Image.Image:
        """Render the single frame at time ``t`` for the given segments."""
        options = options or RenderOptions()
        timeline = self._compile(segments, theme, ctx, canvas, options)
        return self._drawer.render_frame(timeline, t, canvas, clear_color=options.clear_color)

    def render_sequence(
        self,
        segments: Sequence[Segment],
        theme: ResolvedTheme,
        ctx: ResolutionContext,
        canvas: Canvas,
        *,
        options: RenderOptions | None = None,
        start: float | None = None,
        end: float | None = None,
    ) -> list[Image.Image]:
        """Render frames from ``start`` to ``end`` inclusive at ``options.fps``."""
        options = options or RenderOptions()
        timeline = self._compile(segments, theme, ctx, canvas, options)
        if start is None:
            start = min((segment.start for segment in segments), default=0.0)
        if end is None:
            end = max((segment.end for segment in segments), default=1.0)
        return self._drawer.render_sequence(
            timeline,
            canvas,
            fps=options.fps,
            clear_color=options.clear_color,
            start=start,
            end=end,
        )
