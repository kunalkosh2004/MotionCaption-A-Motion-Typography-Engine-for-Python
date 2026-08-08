"""The compiler frontend: CaptionRequest -> SubtitleTimeline.

Stages are pure transforms in ``stages.py``; ``Compiler``/``compile`` are the
composition root. The IR is produced here and consumed by every backend.
"""

from __future__ import annotations

from motion_caption.compiler.engine import Compiler, compile, default_compiler
from motion_caption.compiler.request import request_from_segments
from motion_caption.compiler.resolve import design_context, resolve_typography, word_typography

__all__ = [
    "Compiler",
    "compile",
    "default_compiler",
    "design_context",
    "request_from_segments",
    "resolve_typography",
    "word_typography",
]
