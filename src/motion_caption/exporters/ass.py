"""ASS exporter: bake the sampled keyframe timeline into override tags.

ASS has no easing primitives, so the exporter re-samples each word's
``RegionTimeline`` at ``fps`` and emits chained ``\\t`` override segments —
piecewise-linear "baked acceleration segments" — plus the base tags
(``\\pos``, ``\\fscx/fscy``, ``\\frz``, ``\\blur``, ``\\alpha``, ``\\c``).
One Dialogue line per segment carries the per-word override blocks.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from motion_caption.animations import AnimationConfig, build_word_items
from motion_caption.canvas import Canvas
from motion_caption.exporters.protocol import ExporterResult
from motion_caption.ir.timeline import AnimationTrack, SubtitleTimeline
from motion_caption.layout import LayoutOptions, lay_out
from motion_caption.models.color import Color
from motion_caption.models.keyframe import Region
from motion_caption.models.transcript import Segment
from motion_caption.models.units import ResolutionContext
from motion_caption.placement import Face, PlacementConfig, place
from motion_caption.themes.spec import ResolvedTheme
from motion_caption.typography.measure import TextMeasurer
from motion_caption.typography.style import TextAlign


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis == 100:
        centis = 0
        whole += 1
    if whole == 60:
        whole = 0
        minutes += 1
    return f"{hours}:{minutes:02d}:{whole:02d}.{centis:02d}"


def _ass_alpha(opacity: float) -> str:
    return f"&H{round((1.0 - opacity) * 255):02X}&"


def _ass_rgb(color: Color) -> str:
    return f"&H{color.b:02X}{color.g:02X}{color.r:02X}&"


def _ass_color(color: Color) -> str:
    return color.with_alpha(0).as_ass()


def _region_tags(region: Region, x: float, y: float, color: Color | None) -> str:
    tags = [f"\\pos({x:g},{y:g})"]
    tags.append(f"\\fscx{region.scale.x * 100:g}\\fscy{region.scale.y * 100:g}")
    if region.rotation:
        tags.append(f"\\frz{region.rotation:g}")
    if region.blur > 0.0:
        tags.append(f"\\blur{region.blur:g}")
    if color is not None:
        tags.append(f"\\c{_ass_rgb(color)}")
    tags.append(f"\\alpha{_ass_alpha(region.opacity)}")
    return "".join(tags)


def _bake(
    item,
    x: float,
    y: float,
    fps: int,
    color: Color | None,
) -> str:
    start = item.region.start
    end = item.region.end
    samples = max(1, round((end - start) * fps))
    first = item.region.sample(start)
    parts = ["{" + _region_tags(first, x, y, color) + "}"]
    previous_t = start
    for index in range(1, samples + 1):
        t = start + (end - start) * index / samples
        region = item.region.sample(t)
        parts.append(f"{{\\t({previous_t:g},{t:g},{_region_tags(region, x, y, color)})}}")
        previous_t = t
    return "".join(parts)


def _bake_track(
    track: AnimationTrack,
    x: float,
    y: float,
    fps: int,
    color: Color | None,
) -> str:
    """Bake an IR ``AnimationTrack`` into chained ``\\t`` override segments."""
    start = track.start
    end = track.end
    samples = max(1, round((end - start) * fps))
    first = track.sample(start)
    parts = ["{" + _region_tags(first, x, y, color) + "}"]
    previous_t = start
    for index in range(1, samples + 1):
        t = start + (end - start) * index / samples
        region = track.sample(t)
        parts.append(f"{{\\t({previous_t:g},{t:g},{_region_tags(region, x, y, color)})}}")
        previous_t = t
    return "".join(parts)


def _word_positions(
    segment: Segment,
    theme: ResolvedTheme,
    ctx: ResolutionContext,
    canvas: Canvas,
    measurer: TextMeasurer,
    options: AssOptions,
) -> list[tuple[float, float]]:
    block = measurer.measure_words(
        [word.text for word in segment.words],
        theme.base_style,
        ctx,
        max_width=options.layout.max_width,
    )
    placed = lay_out(block, canvas, options.layout, ctx)
    placed = place(placed, canvas, config=options.placement, faces=options.faces)
    return [(word.box.left, word.box.top) for line in placed.block.lines for word in line.words]


def _word_color(item, theme: ResolvedTheme):
    appearance = theme.emphasis.get(item.emphasis)
    if appearance is not None and appearance.color is not None:
        return appearance.color
    return None


def _style_block(
    theme: ResolvedTheme,
    ctx: ResolutionContext,
    style_name: str,
) -> str:
    style = theme.base_style
    font = theme.fonts[0]
    fontname = font.family if font is not None else "Helvetica"
    fontsize = style.size.resolve(ctx)
    primary = _ass_color(style.fill.color)
    stroke = style.stroke
    outline_color = _ass_color(stroke.color) if stroke is not None else "&H000000&"
    outline = round(stroke.width.resolve(ctx)) if stroke is not None else 0
    shadow = style.shadow
    back_color = _ass_color(shadow.color) if shadow is not None else "&H000000&"
    shadow_px = round(shadow.offset.dy.resolve(ctx)) if shadow is not None else 0
    bold = -1 if font is not None and font.weight >= 700 else 0
    alignment = {TextAlign.LEFT: 1, TextAlign.CENTER: 2, TextAlign.RIGHT: 3}.get(style.align, 2)
    values = [
        style_name,
        fontname,
        f"{fontsize:g}",
        primary,
        primary,
        outline_color,
        back_color,
        str(bold),
        "0",
        "0",
        "0",
        "100",
        "100",
        "0",
        "0",
        "1",
        str(outline),
        str(shadow_px),
        str(alignment),
        "10",
        "10",
        "10",
        "1",
    ]
    return "Style: " + ",".join(values)


def _style_block_timeline(timeline: SubtitleTimeline, style_name: str) -> str:
    """ASS style line derived from the timeline's resolved typography."""
    if not timeline.styles:
        fontname = "Helvetica"
        fontsize = 48.0
        primary = "&H00FFFFFF&"
        outline_color = "&H000000&"
        back_color = "&H000000&"
        bold = 0
        outline = 0
        shadow_px = 0
        alignment = 2
    else:
        typography = timeline.styles[0].typography
        scale = timeline.scale
        fontname = typography.font.family or "Helvetica"
        fontsize = typography.font_size * scale
        primary = _ass_color(typography.fill)
        stroke = typography.stroke
        outline_color = _ass_color(stroke.color) if stroke is not None else "&H000000&"
        outline = round(stroke.width * scale) if stroke is not None else 0
        shadow = typography.shadow
        back_color = _ass_color(shadow.color) if shadow is not None else "&H000000&"
        shadow_px = round(shadow.offset_y * scale) if shadow is not None else 0
        bold = -1 if typography.font.weight >= 700 else 0
        alignment = {TextAlign.LEFT: 1, TextAlign.CENTER: 2, TextAlign.RIGHT: 3}.get(
            typography.align, 2
        )
    values = [
        style_name,
        fontname,
        f"{fontsize:g}",
        primary,
        primary,
        outline_color,
        back_color,
        str(bold),
        "0",
        "0",
        "0",
        "100",
        "100",
        "0",
        "0",
        "1",
        str(outline),
        str(shadow_px),
        str(alignment),
        "10",
        "10",
        "10",
        "1",
    ]
    return "Style: " + ",".join(values)


class AssOptions(BaseModel):
    """Selection and tuning for the ASS exporter."""

    fps: int = Field(default=30, gt=0)
    layout: LayoutOptions = Field(default_factory=LayoutOptions)
    placement: PlacementConfig = Field(default_factory=PlacementConfig)
    animation: AnimationConfig = Field(default_factory=AnimationConfig)
    faces: list[Face] = Field(default_factory=list)
    style_name: str = "Default"


class AssExporter:
    """ASS backend: reinterpret a ``SubtitleTimeline`` as override-tag text.

    ASS has no easing primitives, so the exporter re-samples each word's
    ``AnimationTrack`` at ``fps`` and emits chained ``\\t`` override segments —
    piecewise-linear "baked acceleration segments" — plus the base tags
    (``\\pos``, ``\\fscx/fscy``, ``\\frz``, ``\\blur``, ``\\alpha``, ``\\c``).
    One ``Dialogue`` line per ``SubtitleEvent`` carries the per-word blocks.

    Geometry is stored in design-space pixels; everything is multiplied by
    ``timeline.scale`` once (like every backend). The compiler bakes emphasis
    scale into the SCALE track, so ``\\fscx/fscy`` already includes it (the
    legacy exporter did not).
    """

    name = "ass"

    def export(
        self,
        timeline: SubtitleTimeline,
        *,
        fps: int = 30,
        style_name: str = "Default",
    ) -> ExporterResult:
        scale = timeline.scale
        base_fill = timeline.styles[0].typography.fill if timeline.styles else None
        events: list[str] = []
        for event in timeline.events:
            blocks: list[str] = []
            for word in event.words:
                typography = word.typography
                if typography is None and event.style is not None:
                    typography = event.style.typography
                x = word.box.left * scale
                y = word.box.top * scale
                track = word.animation or AnimationTrack()
                color = None
                if (
                    typography is not None
                    and base_fill is not None
                    and typography.fill != base_fill
                ):
                    color = typography.fill
                blocks.append(_bake_track(track, x, y, fps, color) + word.text)
            events.append(
                f"Dialogue: {event.layer},{_ass_time(event.start)},{_ass_time(event.end)},"
                f"{style_name},,0,0,0,,{' '.join(blocks)}"
            )

        header = (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            f"PlayResX: {timeline.resolution.width}\n"
            f"PlayResY: {timeline.resolution.height}\n"
            "ScaledBorderAndShadow: yes\n"
            "\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding\n"
            f"{_style_block_timeline(timeline, style_name)}\n"
            "\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
            "Effect, Text\n"
        )
        return ExporterResult(
            data=header + "\n".join(events),
            media_type="text/plain",
            extension="ass",
        )


def build_ass(
    segments: Sequence[Segment],
    theme: ResolvedTheme,
    ctx: ResolutionContext,
    canvas: Canvas,
    *,
    options: AssOptions | None = None,
) -> str:
    """Render the full ASS document for the given segments and theme."""
    options = options or AssOptions()
    measurer = TextMeasurer()
    items = build_word_items(segments, theme, options.animation)

    events: list[str] = []
    index = 0
    for segment in segments:
        if not segment.words:
            continue
        positions = _word_positions(segment, theme, ctx, canvas, measurer, options)
        words: list[str] = []
        for j, word in enumerate(segment.words):
            item = items[index + j]
            color = _word_color(item, theme)
            x, y = positions[j]
            words.append(_bake(item, x, y, options.fps, color) + word.text)
        index += len(segment.words)
        events.append(
            f"Dialogue: 0,{_ass_time(segment.start)},{_ass_time(segment.end)},"
            f"{options.style_name},,0,0,0,,{' '.join(words)}"
        )

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {canvas.width}\n"
        f"PlayResY: {canvas.height}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"{_style_block(theme, ctx, options.style_name)}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    return header + "\n".join(events)
