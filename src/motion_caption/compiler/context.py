"""The compiler's stage bus: everything stages read and write."""

from __future__ import annotations

from dataclasses import dataclass, field

from motion_caption.canvas import Canvas
from motion_caption.ir.request import CaptionRequest
from motion_caption.ir.timeline import SubtitleTimeline
from motion_caption.ir.typography import ResolvedTypography
from motion_caption.layout.engine import PlacedBlock
from motion_caption.models.transcript import Segment
from motion_caption.models.units import ResolutionContext
from motion_caption.themes.spec import ResolvedTheme, ThemeSpec
from motion_caption.typography.fonts import FontManager


@dataclass
class CompileContext:
    """Accumulator threaded through the compiler's pure stages.

    Each stage owns a slice of the fields and only touches those. Stages are
    deterministic: identical requests produce identical contexts.
    """

    request: CaptionRequest
    fonts: FontManager
    design_ctx: ResolutionContext
    canvas: Canvas

    theme_spec: ThemeSpec | None = None
    theme: ResolvedTheme | None = None
    segments: list[Segment] = field(default_factory=list)
    placed: list[PlacedBlock] = field(default_factory=list)
    base_typography: ResolvedTypography | None = None
    word_items: list[object] = field(default_factory=list)
    timeline: SubtitleTimeline | None = None
