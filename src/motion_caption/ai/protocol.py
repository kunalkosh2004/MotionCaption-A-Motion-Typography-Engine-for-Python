"""The AI provider protocol: annotate a ``CaptionRequest`` -> ``AIContribution``.

AI runs *outside* the deterministic compiler: a provider's output is
precomputed data (``llm_annotations``) attached to the request, and the
compiler prefers it over rule-based behavior when present. Providers are never
imported by core; the ``motion_caption.ai`` entry-point group is the only
wiring. Deterministic fallbacks (rule-based emphasis, segmentation strategies)
run when no provider is configured.
"""

from __future__ import annotations

from typing import Protocol

from motion_caption.ir.request import AIContribution, CaptionRequest


class AIProvider(Protocol):
    """Annotate a request with precomputed AI contributions."""

    name: str

    def annotate(self, request: CaptionRequest) -> AIContribution: ...
