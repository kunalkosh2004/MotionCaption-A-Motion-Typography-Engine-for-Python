"""Reference AI providers (backed by the ``ai`` extra SDKs).

SDK imports happen inside the call functions, so importing this module never
pulls in ``openai`` or ``google.generativeai`` — core stays dependency-free.
Providers translate the transcript into a JSON prompt, call the API, and parse
the response into an ``AIContribution`` (malformed entries are dropped).
"""

from __future__ import annotations

import json
import os

from motion_caption.ir.request import AIContribution, CaptionRequest
from motion_caption.models.transcript import EmphasisMode

_PROMPT = """You are annotating a word-timed subtitle transcript for a caption engine.
Return ONLY a JSON object; every field is optional:
- "importance": {"<word index>": score 0..1}
- "emphasis": {"<word index>": "none"|"low"|"medium"|"high"|"karaoke"}
- "splits": [[<word indices>], ...] — contiguous, non-overlapping groups covering all words
- "theme": a theme name ("clean", "music_video", "cinematic", "sport", "news")
- "emotion": a short mood label

Words (index: text, start, end):
{payload}
"""


def _transcript_payload(request: CaptionRequest) -> list[dict[str, object]]:
    return [
        {"index": index, "text": word.text, "start": word.start, "end": word.end}
        for index, word in enumerate(request.transcript.words)
    ]


def _build_prompt(payload: list[dict[str, object]]) -> str:
    return _PROMPT.replace("{payload}", json.dumps(payload))


def _parse_contribution(content: str) -> AIContribution:
    """Parse a model response into an ``AIContribution`` (defensive).

    Raises ``ValueError`` with a clear message when the model output is not
    valid JSON; malformed individual entries are dropped. A markdown code
    fence around the JSON (some providers wrap output in ```json blocks) is
    tolerated.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"AI provider returned invalid JSON: {content[:80]!r}"
        ) from exc

    importance: dict[int, float] = {}
    for key, value in (payload.get("importance") or {}).items():
        try:
            score = float(value)
            index = int(key)
        except (TypeError, ValueError):
            continue
        if 0.0 <= score <= 1.0:
            importance[index] = score

    emphasis: dict[int, EmphasisMode] = {}
    for key, value in (payload.get("emphasis") or {}).items():
        try:
            emphasis[int(key)] = EmphasisMode(value)
        except (TypeError, ValueError):
            continue

    splits: list[list[int]] = []
    for group in payload.get("splits") or []:
        try:
            indices = [int(index) for index in group]
        except (TypeError, ValueError):
            continue
        if indices:
            splits.append(indices)

    theme = payload.get("theme")
    emotion = payload.get("emotion")
    return AIContribution(
        importance=importance or None,
        emphasis=emphasis or None,
        splits=splits or None,
        theme=theme if isinstance(theme, str) else None,
        emotion=emotion if isinstance(emotion, str) else None,
    )


def _openai_complete(api_key: str, model: str, prompt: str) -> str:
    """Call the OpenAI chat completions API (SDK imported lazily)."""
    import openai

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or ""


def _gemini_generate(api_key: str, model: str, prompt: str) -> str:
    """Call the Gemini API through the modern ``google.genai`` SDK (lazy import).

    ``response_mime_type="application/json"`` forces bare JSON output so the
    response parses directly; no markdown fences are expected.
    """
    from google import genai

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    return response.text or ""


class OpenAIProvider:
    """Reference AI provider backed by the OpenAI chat completions API."""

    name = "openai"

    def __init__(self, api_key: str | None = None, *, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    def annotate(self, request: CaptionRequest) -> AIContribution:
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAIProvider: no api_key; pass one or set OPENAI_API_KEY"
            )
        content = _openai_complete(
            api_key, self.model, _build_prompt(_transcript_payload(request))
        )
        return _parse_contribution(content)


class GeminiProvider:
    """Reference AI provider backed by the Google Generative AI API."""

    name = "gemini"

    def __init__(self, api_key: str | None = None, *, model: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key
        self.model = model

    def annotate(self, request: CaptionRequest) -> AIContribution:
        api_key = self.api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GeminiProvider: no api_key; pass one or set GEMINI_API_KEY"
            )
        content = _gemini_generate(
            api_key, self.model, _build_prompt(_transcript_payload(request))
        )
        return _parse_contribution(content)
