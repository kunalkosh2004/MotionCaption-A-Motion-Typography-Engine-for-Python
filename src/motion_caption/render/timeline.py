"""TimelineRenderer: a dumb rasterizer that draws only from ``SubtitleTimeline``.

The renderer never measures text, resolves lengths, chooses fonts or computes
layout. Everything it needs is already in the IR: ``WordEvent.box`` (absolute
design-space bounds), ``WordEvent.typography`` (resolved fonts and styles) and
``WordEvent.animation`` (keyframed motion that samples to a ``Region``).

Geometry is stored in design-space pixels for ``timeline.resolution``; this
renderer applies ``scale`` once (default ``timeline.scale``) to map design px
onto the output canvas — exactly like a codegen backend materializing for a
target ISA. Rendering is *sampling*, never per-frame authoring.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from motion_caption.canvas import Canvas
from motion_caption.ir.timeline import SubtitleEvent, SubtitleTimeline, WordEvent
from motion_caption.ir.typography import ResolvedTypography
from motion_caption.models.color import Color
from motion_caption.models.geometry import Box
from motion_caption.models.keyframe import Region


def _with_alpha(image: Image.Image, factor: float) -> Image.Image:
    alpha = image.split()[3].point(lambda p: max(0, min(255, round(p * factor))))
    image.putalpha(alpha)
    return image


class TimelineRenderer:
    """Deterministic Pillow rasterizer over a compiled ``SubtitleTimeline``."""

    def __init__(self) -> None:
        self._fonts: dict[tuple[str, int, int], ImageFont.FreeTypeFont] = {}

    def _font(self, path: str, index: int, size: int) -> ImageFont.FreeTypeFont:
        key = (path, index, size)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(path, size, index=index)
        return self._fonts[key]

    # -- drawing primitives ---------------------------------------------------

    def _glyph_image(
        self,
        word: WordEvent,
        text: str,
        color: Color,
        typography: ResolvedTypography,
        scale: float,
    ) -> Image.Image:
        font_size = max(1, int(round(typography.font_size * scale)))
        font = self._font(typography.font.path, typography.font.index, font_size)

        shadow = typography.shadow
        pad = 0.0
        if shadow is not None:
            dx = shadow.offset_x * scale
            dy = shadow.offset_y * scale
            blur = shadow.blur * scale
            pad = max(abs(dx), abs(dy)) + blur
        pad = math.ceil(pad)

        width = math.ceil(word.box.width * scale) + 2 * pad
        height = math.ceil(word.box.height * scale) + 2 * pad
        image = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))

        if shadow is not None and shadow.opacity > 0.0:
            shadow_color = shadow.color.with_alpha(round(255 * shadow.opacity))
            shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
            ImageDraw.Draw(shadow_layer).text(
                (
                    pad + shadow.offset_x * scale,
                    pad + shadow.offset_y * scale,
                ),
                text,
                font=font,
                fill=shadow_color.rgba,
            )
            if shadow.blur > 0.0:
                shadow_layer = shadow_layer.filter(
                    ImageFilter.GaussianBlur(shadow.blur * scale)
                )
            image.alpha_composite(shadow_layer)

        stroke = typography.stroke
        stroke_width = round(stroke.width * scale) if stroke is not None else 0
        stroke_fill = (
            stroke.color.with_alpha(round(255 * stroke.opacity)).rgba
            if stroke is not None
            else None
        )
        ImageDraw.Draw(image).text(
            (pad, pad),
            text,
            font=font,
            fill=color.rgba,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        return image

    def _glow_layer(
        self,
        glyphs: Image.Image,
        region: Region,
        typography: ResolvedTypography,
        scale: float,
    ) -> Image.Image | None:
        glow = typography.glow
        spread = region.glow_spread * scale
        if spread <= 0.0 and glow is not None:
            spread = glow.spread * scale
        opacity = region.glow_opacity
        if glow is not None and glow.opacity > opacity:
            opacity = glow.opacity
        if spread <= 0.0 or opacity <= 0.0:
            return None
        color = (
            region.glow_color
            or (glow.color if glow is not None else None)
            or Color("#FFFFFF")
        )
        mask = glyphs.split()[3].filter(ImageFilter.GaussianBlur(max(0.1, spread)))
        mask = mask.point(lambda p: max(0, min(255, round(p * opacity))))
        layer = Image.new("RGBA", glyphs.size, (color.r, color.g, color.b, 255))
        layer.putalpha(mask)
        return layer

    def _transform(
        self, image: Image.Image, scale: float, rotation: float, blur: float
    ) -> Image.Image:
        width, height = image.size
        scaled = (max(1, round(width * scale)), max(1, round(height * scale)))
        if scaled != image.size:
            image = image.resize(scaled, Image.BICUBIC)
        if rotation:
            image = image.rotate(rotation, resample=Image.BICUBIC, expand=True)
        if blur > 0.0:
            image = image.filter(ImageFilter.GaussianBlur(blur))
        return image

    def _paste_centered(
        self,
        frame: Image.Image,
        image: Image.Image,
        center_x: float,
        center_y: float,
        opacity: float,
    ) -> None:
        if opacity < 1.0:
            image = _with_alpha(image.copy(), opacity)
        frame.alpha_composite(
            image,
            (round(center_x - image.width / 2), round(center_y - image.height / 2)),
        )

    def _draw_word(self, frame: Image.Image, word: WordEvent, region: Region, scale: float) -> None:
        typography = word.typography
        assert typography is not None
        text = word.text.upper() if typography.uppercase else word.text
        color = region.color or typography.fill
        glyphs = self._glyph_image(word, text, color, typography, scale)
        glow = self._glow_layer(glyphs, region, typography, scale)
        scale_factor = region.scale.x
        center_x = (word.box.center_x + region.position.x) * scale
        center_y = (word.box.center_y + region.position.y) * scale
        if glow is not None:
            transformed_glow = self._transform(
                glow, scale_factor, region.rotation, region.blur * scale
            )
            self._paste_centered(frame, transformed_glow, center_x, center_y, region.opacity)
        transformed = self._transform(glyphs, scale_factor, region.rotation, region.blur * scale)
        self._paste_centered(frame, transformed, center_x, center_y, region.opacity)

    def _draw_background(
        self,
        frame: Image.Image,
        event: SubtitleEvent,
        opacity: float,
        scale: float,
    ) -> None:
        style = event.style
        if style is None or style.typography.background is None:
            return
        background = style.typography.background
        box = event.region.box
        padding = background.padding
        region = Box(
            (box.left - padding.left) * scale,
            (box.top - padding.top) * scale,
            (box.right + padding.right) * scale,
            (box.bottom + padding.bottom) * scale,
        )
        if background.fill_gradient is not None:
            color = background.fill_gradient.sample(0.5)
        elif background.fill is not None:
            color = background.fill
        else:
            return
        fill = (color.r, color.g, color.b, round(255 * background.opacity * opacity))
        radius = background.corner_radius * scale
        border = background.border
        outline = border.color.rgba if border is not None else None
        outline_width = round(border.width * scale) if border is not None else 0
        ImageDraw.Draw(frame).rounded_rectangle(
            (region.left, region.top, region.right, region.bottom),
            radius=radius,
            fill=fill,
            outline=outline,
            width=outline_width,
        )

    # -- public API -----------------------------------------------------------

    def render_frame(
        self,
        timeline: SubtitleTimeline,
        t: float,
        canvas: Canvas,
        *,
        clear_color: tuple[int, int, int, int] = (0, 0, 0, 0),
        scale: float | None = None,
    ) -> Image.Image:
        """Rasterize the events overlapping ``t`` onto an RGBA canvas."""
        scale = timeline.scale if scale is None else scale
        frame = Image.new("RGBA", (canvas.width, canvas.height), clear_color)
        for event in timeline.events_at(t):
            regions = [word.region_at(t) for word in event.words]
            block_opacity = max((region.opacity for region in regions), default=0.0)
            if block_opacity > 0.0:
                self._draw_background(frame, event, block_opacity, scale)
            for word, region in zip(event.words, regions, strict=True):
                if region.opacity <= 0.0 or word.typography is None:
                    continue
                self._draw_word(frame, word, region, scale)
        return frame

    def render_sequence(
        self,
        timeline: SubtitleTimeline,
        canvas: Canvas,
        *,
        fps: int = 30,
        clear_color: tuple[int, int, int, int] = (0, 0, 0, 0),
        start: float | None = None,
        end: float | None = None,
        scale: float | None = None,
    ) -> list[Image.Image]:
        """Render frames from ``start`` to ``end`` inclusive at ``fps``."""
        if start is None:
            start = timeline.start
        if end is None:
            end = timeline.end
        step = 1.0 / fps
        frames: list[Image.Image] = []
        t = start
        while t <= end + 1e-9:
            frames.append(
                self.render_frame(timeline, t, canvas, clear_color=clear_color, scale=scale)
            )
            t += step
        return frames
