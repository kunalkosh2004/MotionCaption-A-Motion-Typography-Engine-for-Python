"""Typography resolution: ``TextStyle`` -> ``ResolvedTypography``.

The typography stage is where every ``Length`` in a style becomes a design-px
float and the font stack is bound to a concrete face. Downstream (layout is
separate; renderers/exporters) never re-resolve a length or consult a font
catalog.

Emphasis appearances are applied here too (color, glow, uppercase, weight,
letter-spacing); the emphasis *scale* delta is baked into the animation stage
as a keyframed SCALE track, because scale is motion, not style.
"""

from __future__ import annotations

from motion_caption.canvas import Canvas
from motion_caption.ir.typography import (
    ResolvedBackground,
    ResolvedBorder,
    ResolvedFont,
    ResolvedGlow,
    ResolvedPadding,
    ResolvedShadow,
    ResolvedStroke,
    ResolvedTypography,
)
from motion_caption.models.units import ResolutionContext
from motion_caption.themes.spec import EmphasisAppearance, ResolvedTheme
from motion_caption.typography.fonts import FontFile, FontManager, FontRef
from motion_caption.typography.measure import MeasuredWord


def design_context(request) -> tuple[ResolutionContext, Canvas]:
    """The design-space resolution context and canvas for a request.

    The compiler compiles against the design reference; exporters scale the
    resulting timeline to the requested output canvas via ``timeline.scale``.
    """
    design = request.resolved_design
    reference = design.reference
    ctx = ResolutionContext(canvas=reference, design=design)
    canvas = Canvas(width=reference.width, height=reference.height)
    return ctx, canvas


def _resolved_font(face: FontFile) -> ResolvedFont:
    return ResolvedFont(
        family=face.family,
        weight=face.weight,
        italic=face.italic,
        path=str(face.path),
        index=face.index,
    )


def resolve_typography(theme: ResolvedTheme, ctx: ResolutionContext) -> ResolvedTypography:
    """Resolve a resolved theme's base style into design-px typography."""
    if not theme.fonts:
        raise ValueError(
            "theme resolved to no fonts; check the theme's font stack "
            f"(stack={theme.spec.font_stack!r})"
        )
    style = theme.base_style
    font_size = style.size.resolve(ctx)
    text_ctx = ctx.model_copy(update={"font_size": font_size})

    stroke = None
    if style.stroke is not None:
        stroke = ResolvedStroke(
            width=style.stroke.width.resolve(text_ctx),
            color=style.stroke.color,
            opacity=style.stroke.opacity,
        )

    shadow = None
    if style.shadow is not None:
        s = style.shadow
        shadow = ResolvedShadow(
            offset_x=s.offset.dx.resolve(text_ctx),
            offset_y=s.offset.dy.resolve(text_ctx),
            blur=s.blur.resolve(text_ctx),
            color=s.color,
            opacity=s.opacity,
        )

    glow = None
    if style.glow is not None:
        g = style.glow
        glow = ResolvedGlow(
            color=g.color,
            spread=g.spread.resolve(text_ctx),
            opacity=g.opacity,
        )

    background = None
    if style.background is not None:
        b = style.background
        padding = b.padding.resolve(text_ctx)
        border = None
        if b.border is not None:
            border = ResolvedBorder(
                width=b.border.width.resolve(text_ctx),
                color=b.border.color,
            )
        background = ResolvedBackground(
            fill=b.fill.color if b.fill is not None else None,
            fill_gradient=b.fill.gradient if b.fill is not None else None,
            padding=ResolvedPadding(
                left=padding.left,
                top=padding.top,
                right=padding.right,
                bottom=padding.bottom,
            ),
            corner_radius=b.corner_radius.resolve(text_ctx),
            border=border,
            opacity=b.opacity,
            blur=b.blur.resolve(text_ctx),
        )

    return ResolvedTypography(
        font=_resolved_font(theme.fonts[0]),
        font_size=font_size,
        fill=style.fill.color,
        fill_gradient=style.fill.gradient if style.fill.uses_gradient else None,
        stroke=stroke,
        shadow=shadow,
        glow=glow,
        background=background,
        letter_spacing=style.letter_spacing.resolve(text_ctx),
        word_spacing=style.word_spacing.resolve(text_ctx),
        line_height=style.line_height.resolve(text_ctx),
        opacity=style.opacity,
        blur=style.blur.resolve(text_ctx),
        uppercase=style.uppercase,
        align=style.align,
    )


def _face_for_measured(theme: ResolvedTheme, path: str, index: int) -> FontFile | None:
    for face in theme.fonts:
        if str(face.path) == path and face.index == index:
            return face
    return None


def word_typography(
    base: ResolvedTypography,
    measured: MeasuredWord | None,
    appearance: EmphasisAppearance | None,
    theme: ResolvedTheme,
    ctx: ResolutionContext,
    *,
    fonts: FontManager,
) -> ResolvedTypography:
    """Per-word typography: measured face plus emphasis-appearance deltas.

    Emphasis ``scale`` is intentionally NOT applied here — the animation stage
    bakes it into the SCALE keyframe track so renderers treat it as motion.
    """
    typo = base
    if measured is not None:
        face = _face_for_measured(theme, measured.font_path, measured.font_index)
        if face is not None:
            typo = typo.model_copy(update={"font": _resolved_font(face)})
    if appearance is None:
        return typo

    updates: dict = {}
    if appearance.color is not None:
        updates["fill"] = appearance.color
    if appearance.uppercase is not None:
        updates["uppercase"] = appearance.uppercase
    if appearance.letter_spacing is not None:
        updates["letter_spacing"] = appearance.letter_spacing.resolve(
            ctx.model_copy(update={"font_size": base.font_size})
        )
    if appearance.glow is not None:
        glow = appearance.glow
        updates["glow"] = ResolvedGlow(
            color=glow.color,
            spread=glow.spread.resolve(ctx),
            opacity=glow.opacity,
        )
    if appearance.weight is not None and appearance.weight != base.font.weight:
        face = fonts.resolve(FontRef(family=base.font.family, weight=appearance.weight))
        if face is not None:
            updates["font"] = _resolved_font(face)
    if not updates:
        return typo
    return typo.model_copy(update=updates)
