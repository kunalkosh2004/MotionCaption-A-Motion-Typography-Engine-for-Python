"""ASS exporter: reinterpret a compiled ``SubtitleTimeline`` as override tags.

ASS has no easing primitives, so the exporter re-samples each word's
``AnimationTrack`` at ``fps`` and emits chained ``\\t`` override segments —
piecewise-linear "baked acceleration segments" — plus the base tags
(``\\pos``, ``\\fscx/fscy``, ``\\frz``, ``\\blur``, ``\\alpha``, ``\\c``).
One ``Dialogue`` line per ``SubtitleEvent`` carries the per-word blocks.

``build_ass`` keeps its historical signature for backward compatibility: it
compiles the given segments into a ``SubtitleTimeline`` and delegates to
``AssExporter``.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from motion_caption.animations import AnimationConfig
from motion_caption.canvas import Canvas
from motion_caption.compiler.engine import default_compiler
from motion_caption.compiler.request import request_from_segments
from motion_caption.exporters.protocol import ExporterResult
from motion_caption.ir.timeline import AnimationTrack, SubtitleTimeline
from motion_caption.layout import LayoutOptions
from motion_caption.models.color import Color
from motion_caption.models.keyframe import Region
from motion_caption.models.transcript import Segment
from motion_caption.models.units import ResolutionContext
from motion_caption.placement import Face, PlacementConfig
from motion_caption.themes.spec import ResolvedTheme
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
    """
    Convert opacity [0, 1] to ASS alpha.

    ASS alpha:
        00 = fully opaque
        FF = fully transparent

    Clamp the value so invalid values such as
    -9 or 256 can never be emitted.
    """
    opacity = max(0.0, min(1.0, float(opacity)))

    alpha = round((1.0 - opacity) * 255)

    alpha = max(0, min(255, alpha))

    return f"&H{alpha:02X}&"


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


def _bake_track(
    track: AnimationTrack,
    x: float,
    y: float,
    fps: int,
    color: Color | None,
    event_start: float = 0.0,
) -> str:
    """Bake an AnimationTrack into compact ASS transform segments.

    ASS transform timestamps are milliseconds relative to the
    beginning of the Dialogue event.
    """

    start = track.start
    end = track.end

    if end <= start:
        region = track.sample(start)
        return "{" + _region_tags(region, x, y, color) + "}"

    # Sample the animation.
    samples = max(1, round((end - start) * fps))

    regions = [
        track.sample(
            start + (end - start) * i / samples
        )
        for i in range(samples + 1)
    ]

    first = regions[0]

    parts = [
        "{" + _region_tags(first, x, y, color) + "}"
    ]

    def changed(a, b, epsilon=1e-4):
        return abs(a - b) > epsilon

    previous = regions[0]
    previous_t = start

    for index in range(1, len(regions)):
        region = regions[index]

        # Skip completely identical samples.
        if (
            not changed(region.scale.x, previous.scale.x)
            and not changed(region.scale.y, previous.scale.y)
            and not changed(region.rotation, previous.rotation)
            and not changed(region.blur, previous.blur)
            and not changed(region.opacity, previous.opacity)
        ):
            continue

        t = start + (end - start) * index / samples

        t1 = max(
            0,
            round((previous_t - event_start) * 1000),
        )

        t2 = max(
            t1,
            round((t - event_start) * 1000),
        )

        tags = []

        if changed(region.scale.x, previous.scale.x):
            tags.append(
                f"\\fscx{region.scale.x * 100:g}"
            )

        if changed(region.scale.y, previous.scale.y):
            tags.append(
                f"\\fscy{region.scale.y * 100:g}"
            )

        if changed(region.rotation, previous.rotation):
            tags.append(
                f"\\frz{region.rotation:g}"
            )

        if changed(region.blur, previous.blur):
            tags.append(
                f"\\blur{region.blur:g}"
            )

        if changed(region.opacity, previous.opacity):
            tags.append(
                f"\\alpha{_ass_alpha(region.opacity)}"
            )

        if tags and t2 > t1:
            parts.append(
                f"{{\\t({t1},{t2},{''.join(tags)})}}"
            )

        previous = region
        previous_t = t

    return "".join(parts)


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
    """Selection and tuning for the ASS exporter.

    ``layout``/``placement``/``animation``/``faces`` configure the compile
    (passed through to ``CaptionRequest``); ``fps`` and ``style_name`` tune
    the ASS output.
    """

    fps: int = Field(default=30, gt=0)
    layout: LayoutOptions = Field(default_factory=LayoutOptions)
    placement: PlacementConfig = Field(default_factory=PlacementConfig)
    animation: AnimationConfig = Field(default_factory=AnimationConfig)
    faces: list[Face] = Field(default_factory=list)
    style_name: str = "Default"


class AssExporter:
    """ASS backend: reinterpret a ``SubtitleTimeline`` as override-tag text.

    Geometry is stored in design-space pixels; everything is multiplied by
    ``timeline.scale`` once (like every backend). The compiler bakes emphasis
    scale into the SCALE track, so ``\\fscx/fscy`` already includes it.
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
                blocks.append(
                    _bake_track(
                        track,
                        x,
                        y,
                        fps,
                        color,
                        event_start=event.start,
                    )
                    + word.text
                )
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
    """Compile the segments and export ASS (backward-compatible facade)."""
    options = options or AssOptions()
    request = request_from_segments(
        segments,
        theme,
        ctx,
        canvas,
        layout=options.layout,
        placement=options.placement,
        animation=options.animation,
        faces=options.faces,
    )
    timeline = default_compiler().compile(request)
    result = AssExporter().export(timeline, fps=options.fps, style_name=options.style_name)
    if not isinstance(result.data, str):
        raise TypeError(
            f"ASS exporter produced non-text output: {type(result.data).__name__}"
        )
    return result.data
