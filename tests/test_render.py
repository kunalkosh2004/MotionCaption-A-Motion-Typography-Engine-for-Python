"""Tests for the dumb TimelineRenderer and the CaptionRenderer facade.

The facade must keep the old public API while compiling internally; the
TimelineRenderer must draw only what a compiled SubtitleTimeline says.
"""

from __future__ import annotations

import pytest
from PIL import Image

from motion_caption.animations import AnimationConfig
from motion_caption.canvas import Canvas
from motion_caption.compiler import Compiler
from motion_caption.ir import CaptionRequest
from motion_caption.models.transcript import EmphasisMode, Segment, Transcript, Word, WordTimestamp
from motion_caption.models.units import DesignSpace, Resolution, ResolutionContext
from motion_caption.render import CaptionRenderer, RenderOptions, TimelineRenderer
from motion_caption.themes import resolve_theme
from motion_caption.themes.spec import ThemeSpec
from motion_caption.typography.fonts import FontRef, FontStack


def _theme(any_font) -> ThemeSpec:
    return ThemeSpec(
        name="render_test",
        font_stack=FontStack(fonts=[FontRef(family=any_font.family, weight=any_font.weight)]),
        style={
            "size": "48px",
            "fill": {"color": "#FFFFFF"},
            "shadow": {"offset": {"dx": "2px", "dy": "2px"}, "blur": "2px", "opacity": 0.6},
        },
        emphasis={
            EmphasisMode.HIGH: {"scale": 1.2},
        },
    )


def _segments(text: str = "Hello motion typography", *, tail: float = 0.0) -> list[Segment]:
    """Word-bounded segments with an optional display tail after the last word."""
    tokens = text.split()
    words: list[Word] = []
    cursor = 0.0
    for token in tokens:
        words.append(Word(text=token, start=cursor, end=cursor + 0.8))
        cursor += 1.0
    end = words[-1].end + tail
    return [Segment(text=text, start=0.0, end=end, words=words)]


@pytest.fixture
def theme(any_font):
    return resolve_theme(_theme(any_font))


def _canvas_ctx(canvas: Canvas) -> tuple[Canvas, ResolutionContext]:
    return canvas, ResolutionContext(canvas=canvas.resolution)


class TestCaptionRendererFacade:
    def test_renders_deterministic_frames(self, theme):
        canvas, ctx = _canvas_ctx(Canvas.from_standard("720p"))
        renderer = CaptionRenderer()
        segments = _segments()
        a = renderer.render_frame(segments, theme, ctx, canvas, t=1.2)
        b = renderer.render_frame(segments, theme, ctx, canvas, t=1.2)
        assert a.size == (1280, 720)
        assert a.mode == "RGBA"
        assert a.tobytes() == b.tobytes()

    def test_empty_frame_outside_segment_window(self, theme):
        canvas, ctx = _canvas_ctx(Canvas.from_standard("1080p"))
        renderer = CaptionRenderer()
        segments = _segments()  # window [0.0, 2.8]
        empty = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        before = renderer.render_frame(segments, theme, ctx, canvas, t=-1.0)
        after = renderer.render_frame(segments, theme, ctx, canvas, t=5.0)
        assert before.tobytes() == empty.tobytes()
        assert after.tobytes() == empty.tobytes()

    def test_frame_visible_inside_window(self, theme):
        canvas, ctx = _canvas_ctx(Canvas.from_standard("1080p"))
        renderer = CaptionRenderer()
        empty = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        frame = renderer.render_frame(_segments(), theme, ctx, canvas, t=1.1)
        assert frame.tobytes() != empty.tobytes()

    def test_segment_window_includes_display_tail(self, theme):
        """A caption whose end is past its last word stays on screen through the tail."""
        canvas, ctx = _canvas_ctx(Canvas.from_standard("1080p"))
        renderer = CaptionRenderer()
        segments = _segments(tail=1.0)  # last word ends 2.2, segment end 3.2
        empty = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        frame = renderer.render_frame(segments, theme, ctx, canvas, t=2.8)
        assert frame.tobytes() != empty.tobytes()

    def test_static_strategy_bounded_to_event_window(self, theme):
        """'none'/static words are only drawn while their event is on screen."""
        canvas, ctx = _canvas_ctx(Canvas.from_standard("1080p"))
        renderer = CaptionRenderer()
        segments = _segments()
        empty = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        options = RenderOptions(animation=AnimationConfig(strategy="none"))
        outside = renderer.render_frame(segments, theme, ctx, canvas, t=10.0, options=options)
        inside = renderer.render_frame(segments, theme, ctx, canvas, t=1.1, options=options)
        assert outside.tobytes() == empty.tobytes()
        assert inside.tobytes() != empty.tobytes()

    def test_empty_segments_return_blank_frame(self, theme):
        canvas, ctx = _canvas_ctx(Canvas.from_standard("1080p"))
        renderer = CaptionRenderer()
        empty = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        frame = renderer.render_frame([], theme, ctx, canvas, t=0.5)
        assert frame.tobytes() == empty.tobytes()

    def test_base_glow_is_rendered(self, any_font):
        """The resolved base glow (TextStyle.glow) is drawn even when the
        animation strategy isn't 'glow' — the dumb renderer draws exactly what
        ResolvedTypography says."""
        glowing = ThemeSpec(
            name="render_glow_test",
            font_stack=FontStack(
                fonts=[FontRef(family=any_font.family, weight=any_font.weight)]
            ),
            style={
                "size": "48px",
                "fill": {"color": "#FFFFFF"},
                "glow": {"color": "#00E5FF", "spread": "8px", "opacity": 0.8},
            },
        )
        canvas, ctx = _canvas_ctx(Canvas.from_standard("1080p"))
        renderer = CaptionRenderer()
        segments = _segments()
        plain = renderer.render_frame(segments, resolve_theme(_theme(any_font)), ctx, canvas, t=1.1)
        with_glow = renderer.render_frame(segments, resolve_theme(glowing), ctx, canvas, t=1.1)
        assert plain.tobytes() != with_glow.tobytes()

    def test_render_sequence_frame_count(self, theme):
        canvas, ctx = _canvas_ctx(Canvas.from_standard("1080p"))
        renderer = CaptionRenderer()
        frames = renderer.render_sequence(
            _segments(),
            theme,
            ctx,
            canvas,
            options=RenderOptions(fps=10),
            start=0.0,
            end=1.0,
        )
        assert len(frames) == 11


class TestTimelineRenderer:
    def test_consumes_compiled_timeline_at_scale(self, any_font):
        spec = _theme(any_font)
        transcript = Transcript(
            words=[
                WordTimestamp(text="Hello", start=0.0, end=0.8),
                WordTimestamp(text="motion", start=0.9, end=1.7),
                WordTimestamp(text="typography", start=1.8, end=2.6),
            ]
        )
        request = CaptionRequest(
            transcript=transcript,
            theme=spec,
            resolution=Resolution(width=3840, height=2160),
            design=DesignSpace(reference=Resolution(width=1920, height=1080)),
        )
        timeline = Compiler().compile(request)
        assert timeline.scale == pytest.approx(2.0)
        canvas = Canvas(width=3840, height=2160)
        frame = TimelineRenderer().render_frame(timeline, t=1.3, canvas=canvas)
        assert frame.size == (3840, 2160)

    def test_events_filtered_by_time(self, any_font):
        spec = _theme(any_font)
        request = CaptionRequest(
            transcript=Transcript(words=[WordTimestamp(text="Hello", start=0.0, end=0.8)]),
            theme=spec,
        )
        timeline = Compiler().compile(request)
        canvas = Canvas.from_standard("1080p")
        empty = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        renderer = TimelineRenderer()
        outside = renderer.render_frame(timeline, t=99.0, canvas=canvas)
        inside = renderer.render_frame(timeline, t=0.4, canvas=canvas)
        assert outside.tobytes() == empty.tobytes()
        assert inside.tobytes() != empty.tobytes()
