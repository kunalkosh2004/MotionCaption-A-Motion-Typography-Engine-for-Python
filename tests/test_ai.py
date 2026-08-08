"""Tests for the AI seam: protocol, registry, annotate helper, and providers."""

from __future__ import annotations

import json

import pytest

from motion_caption.ai import AI_REGISTRY, annotate, providers
from motion_caption.ir import AIContribution, CaptionRequest
from motion_caption.models.transcript import EmphasisMode, Transcript, WordTimestamp


def _transcript(text: str = "Hello motion typography") -> Transcript:
    tokens = text.split()
    words = []
    cursor = 0.0
    for token in tokens:
        words.append(WordTimestamp(text=token, start=cursor, end=cursor + 0.8))
        cursor += 1.0
    return Transcript(words=words)


def _request(**overrides) -> CaptionRequest:
    data = {"transcript": _transcript()}
    data.update(overrides)
    return CaptionRequest(**data)


class _FakeProvider:
    name = "fake"

    def __init__(self, contribution: AIContribution) -> None:
        self._contribution = contribution

    def annotate(self, request: CaptionRequest) -> AIContribution:
        return self._contribution


class TestAIProtocol:
    def test_annotate_helper_sets_annotations(self):
        request = _request()
        provider = _FakeProvider(AIContribution(theme="music_video"))
        annotated = annotate(request, provider)
        assert annotated is not request
        assert annotated.llm_annotations is not None
        assert annotated.llm_annotations.theme == "music_video"
        assert request.llm_annotations is None  # original untouched

    def test_ai_registry_empty_by_default(self):
        assert AI_REGISTRY.keys == []


class TestParseContribution:
    def test_parses_valid_payload(self):
        content = json.dumps(
            {
                "importance": {"0": 0.9},
                "emphasis": {"1": "high"},
                "splits": [[0, 1], [2]],
                "theme": "music_video",
                "emotion": "energetic",
            }
        )
        contribution = providers._parse_contribution(content)
        assert contribution.importance == {0: 0.9}
        assert contribution.emphasis == {1: EmphasisMode.HIGH}
        assert contribution.splits == [[0, 1], [2]]
        assert contribution.theme == "music_video"
        assert contribution.emotion == "energetic"

    def test_ignores_malformed_entries(self):
        content = json.dumps(
            {
                "importance": {"0": 2.5, "1": "x"},
                "emphasis": {"2": "bogus"},
                "splits": [[], [0, "a"]],
                "theme": 42,
            }
        )
        contribution = providers._parse_contribution(content)
        assert contribution.importance is None
        assert contribution.emphasis is None
        assert contribution.splits is None
        assert contribution.theme is None


class TestOpenAIProvider:
    def test_annotate_parses_completion(self, monkeypatch):
        canned = json.dumps({"theme": "music_video", "importance": {"0": 0.9}})
        monkeypatch.setattr(providers, "_openai_complete", lambda *a, **k: canned)
        contribution = providers.OpenAIProvider(api_key="test-key").annotate(_request())
        assert contribution.theme == "music_video"
        assert contribution.importance == {0: 0.9}

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            providers.OpenAIProvider().annotate(_request())


class TestGeminiProvider:
    def test_annotate_parses_generation(self, monkeypatch):
        canned = json.dumps({"emphasis": {"1": "high"}, "splits": [[0, 1], [2]]})
        monkeypatch.setattr(providers, "_gemini_generate", lambda *a, **k: canned)
        contribution = providers.GeminiProvider(api_key="test-key").annotate(_request())
        assert contribution.emphasis == {1: EmphasisMode.HIGH}
        assert contribution.splits == [[0, 1], [2]]

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            providers.GeminiProvider().annotate(_request())


class TestEndToEnd:
    def test_annotated_request_compiles_with_ai_theme(self, any_font, monkeypatch):
        from motion_caption.compiler import compile
        from motion_caption.themes.catalog import THEME_REGISTRY
        from motion_caption.themes.spec import ThemeSpec
        from motion_caption.typography.fonts import FontRef, FontStack

        THEME_REGISTRY.add(
            "ai_test_theme",
            ThemeSpec(
                name="ai_test_theme",
                font_stack=FontStack(
                    fonts=[FontRef(family=any_font.family, weight=any_font.weight)]
                ),
            ),
            overwrite=True,
        )
        canned = json.dumps({"theme": "ai_test_theme"})
        monkeypatch.setattr(providers, "_openai_complete", lambda *a, **k: canned)
        annotated = annotate(_request(), providers.OpenAIProvider(api_key="k"))
        timeline = compile(annotated)
        assert timeline.styles[0].name == "ai_test_theme"
