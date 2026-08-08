"""Shared facade helpers: high-level inputs → ``CaptionRequest``.

Both public facades (``CaptionRenderer`` and ``build_ass``) accept
already-segmented input (``Sequence[Segment]`` + a resolved theme) while the
compiler consumes a ``CaptionRequest``. This helper rebuilds the segments as
a ``Transcript`` and passes them through the compiler with
``llm_annotations.splits`` so the original word grouping is preserved. The
first word's start and the last word's end are clamped to the segment window,
so a caption whose on-screen span extends beyond its spoken words keeps that
window.
"""

from __future__ import annotations

from collections.abc import Sequence

from motion_caption.animations import AnimationConfig
from motion_caption.canvas import Canvas
from motion_caption.ir.request import AIContribution, CaptionRequest, CompileOptions
from motion_caption.layout import LayoutOptions
from motion_caption.models.transcript import EmphasisMode, Segment, Transcript, WordTimestamp
from motion_caption.models.units import ResolutionContext
from motion_caption.placement import Face, PlacementConfig
from motion_caption.themes.spec import ResolvedTheme


def request_from_segments(
    segments: Sequence[Segment],
    theme: ResolvedTheme,
    ctx: ResolutionContext,
    canvas: Canvas,
    *,
    layout: LayoutOptions | None = None,
    placement: PlacementConfig | None = None,
    animation: AnimationConfig | None = None,
    faces: Sequence[Face] = (),
) -> CaptionRequest:
    """Build a ``CaptionRequest`` that reproduces the given segments."""
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
    return CaptionRequest(
        transcript=Transcript(language="en", words=transcript_words),
        faces=list(faces),
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
            animation=animation,
            layout=layout,
            placement=placement,
        ),
    )
