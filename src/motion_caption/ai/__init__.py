"""AI seam: optional providers that annotate a ``CaptionRequest``.

AI never runs inside the compiler. A provider's output is precomputed data
(``AIContribution``) attached to the request as ``llm_annotations``; the
compiler prefers it when present and falls back to deterministic rules
otherwise. Core never imports a provider SDK — reference providers live in
``motion_caption.ai.providers`` behind the ``ai`` extra.
"""

from __future__ import annotations

from motion_caption.ai.protocol import AIProvider
from motion_caption.ai.providers import GeminiProvider, OpenAIProvider
from motion_caption.ir.request import CaptionRequest
from motion_caption.registry import Registry

AI_REGISTRY: Registry[AIProvider] = Registry("ai")

# The built-in reference providers register themselves like every other
# subsystem's built-ins; providers are stateless (the API key is resolved at
# call time), so shared instances are safe.
AI_REGISTRY.add("openai", OpenAIProvider(), overwrite=True)
AI_REGISTRY.add("gemini", GeminiProvider(), overwrite=True)


def annotate(request: CaptionRequest, provider: AIProvider) -> CaptionRequest:
    """Return a copy of the request with the provider's annotations attached.

    The original request is untouched, so deterministic pipelines can keep a
    clean request and annotate a disposable copy.
    """
    return request.model_copy(update={"llm_annotations": provider.annotate(request)})


__all__ = [
    "AIProvider",
    "AI_REGISTRY",
    "annotate",
]
