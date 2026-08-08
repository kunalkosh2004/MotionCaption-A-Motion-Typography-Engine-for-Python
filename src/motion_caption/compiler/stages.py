"""The compiler's pure pipeline stages.

Each stage is a deterministic transform ``CompileContext -> None`` (mutating
its own slice of the context). Stages are individually replaceable: the
segmentation, emphasis, animation and placement stages dispatch through their
registries; theme resolution goes through the theme registry. Nothing here
touches I/O.

    normalize -> segment -> emphasize -> pace -> theme -> typography
        -> measure_layout -> animate -> place -> assemble -> SubtitleTimeline
"""

from __future__ import annotations

from collections.abc import Iterable

from motion_caption.animations import AnimationConfig, WordItem, build_word_items
from motion_caption.compiler.context import CompileContext
from motion_caption.compiler.resolve import resolve_typography, word_typography
from motion_caption.emphasis import apply_emphasis
from motion_caption.ir.request import AIContribution, CaptionRequest
from motion_caption.ir.timeline import (
    AnimationTrack,
    PlacementRegion,
    StyleTrack,
    SubtitleEvent,
    SubtitleTimeline,
    Track,
    WordEvent,
)
from motion_caption.layout import LayoutOptions, lay_out
from motion_caption.models.geometry import Box, Point
from motion_caption.models.keyframe import Keyframe, KeyframeTimeline, PropertyKind, RegionTimeline
from motion_caption.models.transcript import Segment, Word
from motion_caption.placement import PlacementConfig, place
from motion_caption.reading import adjust_segments
from motion_caption.segmentation import SegmentationConfig, segment_transcript
from motion_caption.themes import load_theme, resolve_theme
from motion_caption.themes.spec import EmphasisAppearance, ThemeSpec
from motion_caption.typography.measure import TextMeasurer


def normalize(ctx: CompileContext) -> None:
    """Resolve defaults: theme (spec or name, AI recommendation fallback)."""
    request = ctx.request
    theme_value: object = request.theme
    if (
        theme_value is None
        and request.llm_annotations is not None
        and request.llm_annotations.theme
    ):
        theme_value = request.llm_annotations.theme
    if isinstance(theme_value, ThemeSpec):
        spec = theme_value
    else:
        name = theme_value or "clean"
        spec = load_theme(str(name))
    ctx.theme_spec = spec


def _segments_from_splits(transcript, splits: list[list[int]]) -> list[Segment]:
    tokens = transcript.words
    result: list[Segment] = []
    for group in splits:
        words = [tokens[index] for index in group if 0 <= index < len(tokens)]
        if not words:
            continue
        result.append(
            Segment(
                text=" ".join(w.text for w in words),
                start=words[0].start,
                end=words[-1].end,
                words=[Word(text=w.text, start=w.start, end=w.end) for w in words],
            )
        )
    return result


def segment(ctx: CompileContext) -> None:
    request = ctx.request
    options = request.resolved_options
    annotations = request.llm_annotations
    if annotations is not None and annotations.splits is not None:
        ctx.segments = _segments_from_splits(request.transcript, annotations.splits)
        return
    config = options.segmentation or SegmentationConfig(language=request.transcript.language)
    ctx.segments = segment_transcript(request.transcript, config, strategy=options.strategy)


def _apply_ai_overrides(segments: Iterable[Segment], annotations: AIContribution) -> list[Segment]:
    if not annotations.importance and not annotations.emphasis:
        return list(segments)
    importance = annotations.importance or {}
    emphasis = annotations.emphasis or {}
    result: list[Segment] = []
    global_index = 0
    for segment in segments:
        updated: list[Word] = []
        for word in segment.words:
            update: dict = {}
            if global_index in importance:
                update["importance"] = importance[global_index]
            if global_index in emphasis:
                update["emphasis"] = emphasis[global_index]
            updated.append(word.model_copy(update=update) if update else word)
            global_index += 1
        result.append(segment.model_copy(update={"words": updated}))
    return result


def emphasize(ctx: CompileContext) -> None:
    request = ctx.request
    options = request.resolved_options
    segments = apply_emphasis(ctx.segments, karaoke=options.karaoke)
    if request.llm_annotations is not None:
        segments = _apply_ai_overrides(segments, request.llm_annotations)
    ctx.segments = segments


def pace(ctx: CompileContext) -> None:
    options = ctx.request.resolved_options
    if options.reading:
        ctx.segments = adjust_segments(ctx.segments, target_wps=options.target_wps)


def resolve_theme_stage(ctx: CompileContext) -> None:
    assert ctx.theme_spec is not None
    if ctx.theme_cache is not None:
        ctx.theme = ctx.theme_cache.resolve(ctx.theme_spec, ctx.fonts)
    else:
        ctx.theme = resolve_theme(ctx.theme_spec, ctx.fonts)


def resolve_typography_stage(ctx: CompileContext) -> None:
    assert ctx.theme is not None
    ctx.base_typography = resolve_typography(ctx.theme, ctx.design_ctx)


def measure_layout_stage(ctx: CompileContext) -> None:
    assert ctx.theme is not None
    options = ctx.request.resolved_options
    layout_options = options.layout or LayoutOptions()
    measurer = TextMeasurer(ctx.fonts)
    placed = []
    for segment in ctx.segments:
        block = measurer.measure_words(
            [word.text for word in segment.words],
            ctx.theme.base_style,
            ctx.design_ctx,
            max_width=layout_options.max_width,
        )
        placed.append(lay_out(block, ctx.canvas, layout_options, ctx.design_ctx))
    ctx.placed = placed


def animate(ctx: CompileContext) -> None:
    assert ctx.theme is not None
    options = ctx.request.resolved_options
    config = options.animation or AnimationConfig()
    ctx.word_items = build_word_items(ctx.segments, ctx.theme, config)


def _placement_config(request: CaptionRequest) -> PlacementConfig:
    options = request.resolved_options
    if options.placement is not None:
        cfg = options.placement
        updates: dict = {}
        if cfg.safe_area is None and request.safe_area is not None:
            updates["safe_area"] = request.safe_area
        if cfg.platform is None and request.platform is not None:
            updates["platform"] = request.platform
        return cfg.model_copy(update=updates) if updates else cfg
    return PlacementConfig(safe_area=request.safe_area, platform=request.platform)


def place_stage(ctx: CompileContext) -> None:
    request = ctx.request
    config = _placement_config(request)
    ctx.placed = [
        place(placed, ctx.canvas, config=config, faces=request.faces) for placed in ctx.placed
    ]


def _emphasis_appearance(ctx: CompileContext, word: Word) -> EmphasisAppearance | None:
    assert ctx.theme is not None
    return ctx.theme.emphasis.get(word.emphasis)


def _bake_scale(region: RegionTimeline, factor: float) -> RegionTimeline:
    if factor == 1.0 or factor <= 0.0:
        return region
    tracks = dict(region.tracks)
    existing = tracks.get(PropertyKind.SCALE)
    if existing is not None:
        keyframes = [
            keyframe.model_copy(
                update={"value": Point(keyframe.value.x * factor, keyframe.value.y * factor)}
            )
            for keyframe in existing.keyframes
        ]
        tracks[PropertyKind.SCALE] = existing.model_copy(update={"keyframes": keyframes})
    else:
        tracks[PropertyKind.SCALE] = KeyframeTimeline(
            kind=PropertyKind.SCALE,
            keyframes=[
                Keyframe(region.start, Point(factor, factor)),
                Keyframe(max(region.end, region.start + 1e-9), Point(factor, factor)),
            ],
        )
    return region.model_copy(update={"tracks": tracks})


def _to_animation_track(
    region: RegionTimeline,
    appearance: EmphasisAppearance | None,
    config: AnimationConfig,
    start: float,
    end: float,
) -> AnimationTrack:
    factor = appearance.scale if appearance is not None else 1.0
    baked = _bake_scale(region, factor)
    track = AnimationTrack()
    for timeline in baked.tracks.values():
        track.add(timeline)
    duration = max(0.0, end - start)
    in_end = start + duration * config.in_window
    out_start = end - duration * config.out_window
    track.phases = {
        "in": (start, in_end),
        "out": (out_start, end),
        "idle": (in_end, out_start),
    }
    return track


def _speakers_for_segments(
    ctx: CompileContext,
) -> list[str | None]:
    request = ctx.request
    if not request.speaker_tracks:
        return [None] * len(ctx.segments)
    mapping: dict[int, str] = {}
    for track in request.speaker_tracks:
        for index in track.word_indices:
            mapping.setdefault(index, track.id)
    result: list[str | None] = []
    global_index = 0
    for segment in ctx.segments:
        speakers = {
            mapping[global_index + offset]
            for offset in range(len(segment.words))
            if global_index + offset in mapping
        }
        result.append(speakers.pop() if len(speakers) == 1 else None)
        global_index += len(segment.words)
    return result


def _flattened_words(placed) -> list:
    return [word for line in placed.block.lines for word in line.words]


def _group_tracks(events: list[SubtitleEvent]) -> list[Track]:
    builders: dict[tuple[str | None, int], list[SubtitleEvent]] = {}
    for event in events:
        builders.setdefault((event.speaker, event.layer), []).append(event)
    tracks: list[Track] = []
    for (speaker, _layer), group in builders.items():
        tracks.append(Track(name=speaker or "main", speaker=speaker, events=group))
    return tracks


def assemble(ctx: CompileContext) -> None:
    assert ctx.theme is not None
    assert ctx.base_typography is not None
    request = ctx.request
    options = request.resolved_options
    config = options.animation or AnimationConfig()
    speakers = _speakers_for_segments(ctx)
    base_style = StyleTrack(name=ctx.theme_spec.name, typography=ctx.base_typography)

    events: list[SubtitleEvent] = []
    item_index = 0
    for segment_index, segment in enumerate(ctx.segments):
        placed = ctx.placed[segment_index]
        measured_words = _flattened_words(placed)
        event_words: list[WordEvent] = []
        for word_offset, word in enumerate(segment.words):
            item: WordItem = ctx.word_items[item_index + word_offset]  # type: ignore[index]
            measured = measured_words[word_offset] if word_offset < len(measured_words) else None
            appearance = _emphasis_appearance(ctx, word)
            typography = word_typography(
                ctx.base_typography,
                measured,
                appearance,
                ctx.theme,
                ctx.design_ctx,
                fonts=ctx.fonts,
            )
            animation = _to_animation_track(item.region, appearance, config, item.start, item.end)
            event_words.append(
                WordEvent(
                    text=word.text,
                    start=item.start,
                    end=item.end,
                    importance=word.importance,
                    emphasis=word.emphasis,
                    box=measured.box if measured is not None else Box(),
                    typography=typography,
                    animation=animation,
                )
            )
        item_index += len(segment.words)
        speaker = speakers[segment_index]
        events.append(
            SubtitleEvent(
                start=segment.start,
                end=segment.end,
                text=segment.text,
                style=base_style,
                region=PlacementRegion(
                    box=placed.box,
                    anchor=Point(placed.box.center_x, placed.box.center_y),
                    speaker=speaker,
                    layer=0,
                ),
                words=event_words,
                speaker=speaker,
                layer=0,
            )
        )

    resolution = request.resolved_resolution
    design = request.resolved_design
    ctx.timeline = SubtitleTimeline(
        metadata=dict(request.metadata),
        resolution=resolution,
        design=design,
        scale=design.scale_for(resolution),
        styles=[base_style],
        tracks=_group_tracks(events),
    )


PIPELINE = (
    normalize,
    segment,
    emphasize,
    pace,
    resolve_theme_stage,
    resolve_typography_stage,
    measure_layout_stage,
    animate,
    place_stage,
    assemble,
)
