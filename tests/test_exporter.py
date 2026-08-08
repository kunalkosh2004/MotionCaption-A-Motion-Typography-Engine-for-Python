"""Tests for the Exporter protocol and the ASS/JSON backends."""

from __future__ import annotations

import json

from motion_caption import (
    AssOptions,
    Canvas,
    ResolutionContext,
    Segment,
    ThemeSpec,
    Word,
    build_ass,
)
from motion_caption.compiler import Compiler
from motion_caption.compiler.request import request_from_segments
from motion_caption.exporters import EXPORTER_REGISTRY, AssExporter, JsonExporter
from motion_caption.ir import CaptionRequest
from motion_caption.models.transcript import EmphasisMode, Transcript, WordTimestamp
from motion_caption.themes import resolve_theme
from motion_caption.typography.fonts import FontRef, FontStack


def _theme(any_font) -> ThemeSpec:
    return ThemeSpec(
        name="exporter_test",
        font_stack=FontStack(fonts=[FontRef(family=any_font.family, weight=any_font.weight)]),
        style={"size": "48px", "fill": {"color": "#FFFFFF"}},
        emphasis={EmphasisMode.HIGH: {"color": "#00E5FF", "scale": 1.2}},
    )


def _transcript(text: str = "Hello motion typography") -> Transcript:
    tokens = text.split()
    words = []
    cursor = 0.0
    for token in tokens:
        words.append(WordTimestamp(text=token, start=cursor, end=cursor + 0.8))
        cursor += 1.0
    return Transcript(words=words)


def _timeline(any_font, **overrides):
    request = CaptionRequest(transcript=_transcript(), theme=_theme(any_font), **overrides)
    return Compiler().compile(request)


def _segments(text: str = "Hello motion typography") -> list[Segment]:
    tokens = text.split()
    words = []
    cursor = 0.0
    for token in tokens:
        words.append(Word(text=token, start=cursor, end=cursor + 0.8))
        cursor += 1.0
    return [Segment(text=text, start=0.0, end=words[-1].end, words=words)]


class TestAssExporter:
    def test_document_structure(self, any_font):
        timeline = _timeline(any_font)
        result = AssExporter().export(timeline, fps=30)
        assert result.extension == "ass"
        data = result.data
        assert data.startswith("[Script Info]")
        assert "[V4+ Styles]" in data
        assert "[Events]" in data
        assert "Style: " in data
        assert data.count("Dialogue:") == len(timeline.events)
        assert "\\pos(" in data
        assert "\\t(" in data  # baked easing segments
        assert "\\fscx" in data

    def test_emphasis_color_and_scale_emitted(self, any_font):
        timeline = _timeline(any_font, llm_annotations={"emphasis": {0: EmphasisMode.HIGH}})
        data = AssExporter().export(timeline, fps=30).data
        assert "\\c&HFFE500&" in data  # #00E5FF in ASS BGR order
        assert "\\fscx120" in data  # baked 1.2 emphasis scale

    def test_json_round_trip(self, any_font):
        timeline = _timeline(any_font)
        result = JsonExporter().export(timeline)
        assert result.extension == "json"
        assert result.media_type == "application/json"
        data = json.loads(result.data)
        assert data["format_version"] == "1.0"
        assert len(data["tracks"]) == len(timeline.tracks)
        words = [w for track in data["tracks"] for event in track["events"] for w in event["words"]]
        assert len(words) == 3

    def test_registry_dispatches(self, any_font):
        timeline = _timeline(any_font)
        assert "ass" in EXPORTER_REGISTRY.keys
        assert "json" in EXPORTER_REGISTRY.keys
        assert EXPORTER_REGISTRY.get("ass").export(timeline).extension == "ass"
        assert EXPORTER_REGISTRY.get("json").export(timeline).extension == "json"


class TestBuildAssFacade:
    def test_backward_compatible(self, any_font):
        theme = resolve_theme(_theme(any_font))
        canvas = Canvas.from_standard("1080p")
        ctx = ResolutionContext(canvas=canvas.resolution)
        data = build_ass(_segments(), theme, ctx, canvas)
        assert isinstance(data, str)
        assert data.startswith("[Script Info]")
        assert data.count("Dialogue:") == 1

    def test_deterministic(self, any_font):
        theme = resolve_theme(_theme(any_font))
        canvas = Canvas.from_standard("1080p")
        ctx = ResolutionContext(canvas=canvas.resolution)
        segments = _segments()
        a = build_ass(segments, theme, ctx, canvas)
        b = build_ass(segments, theme, ctx, canvas)
        assert a == b

    def test_facade_matches_ir_export(self, any_font):
        theme = resolve_theme(_theme(any_font))
        canvas = Canvas.from_standard("1080p")
        ctx = ResolutionContext(canvas=canvas.resolution)
        segments = _segments()
        options = AssOptions(fps=30, style_name="Default")
        via_facade = build_ass(segments, theme, ctx, canvas, options=options)
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
        timeline = Compiler().compile(request)
        direct = AssExporter().export(timeline, fps=30, style_name="Default").data
        assert via_facade == direct
