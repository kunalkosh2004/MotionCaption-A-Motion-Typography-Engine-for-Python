"""Golden frame tests: the dumb renderer's PNG output, byte-exact.

A rendered frame is the *observable* output of the whole pipeline (compile →
typography → layout → placement → animation → rasterize), so a byte-exact
PNG pins everything a timeline snapshot cannot see: glyph rasterization,
shadow/glow compositing and the background box. Rendering is pinned to the
bundled Roboto and compared as raw PNG bytes; regenerate after intentional
visual changes with:

    MC_UPDATE_SNAPSHOTS=1 .venv/bin/python -m pytest tests/test_golden.py -q

FreeType glyph metrics and rasterization differ per operating system, so the
byte-exact comparison is the macOS reference (where snapshots are
regenerated). The pixel-probe tests below still assert real content on every
platform.
"""

from __future__ import annotations

import io
import sys

import pytest
from PIL import Image

import pinned
import snapshot_utils
from motion_caption.canvas import Canvas
from motion_caption.compiler.engine import Compiler
from motion_caption.models.color import Color
from motion_caption.render.timeline import TimelineRenderer

CANVAS = Canvas.from_standard("1080p")
# Mid-idle of the second caption group [1.6, 2.4): fully in, before fade-out.
SAMPLE_T = 2.0


def _frame(compiler: Compiler, t: float) -> Image.Image:
    timeline = compiler.compile(pinned.golden_request())
    return TimelineRenderer().render_frame(timeline, t, CANVAS)


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="golden PNG is a byte-exact macOS rasterization; regenerate on macOS",
)
def test_golden_frame_snapshot(pinned_compiler: Compiler) -> None:
    """The full frame at mid-idle is byte-identical to the committed PNG."""
    frame = _frame(pinned_compiler, SAMPLE_T)
    assert frame.size == (1920, 1080)
    assert frame.mode == "RGBA"

    buffer = io.BytesIO()
    frame.save(buffer, format="PNG")
    snapshot_utils.assert_bytes_snapshot(buffer.getvalue(), "golden", "golden_frame.png")


def test_frame_is_blank_outside_the_timeline(pinned_compiler: Compiler) -> None:
    """Before the first event nothing is drawn (fully transparent)."""
    frame = _frame(pinned_compiler, -1.0)
    assert max(frame.getchannel("A").getextrema()) == 0


def test_frame_draws_glyphs_and_background_box(pinned_compiler: Compiler) -> None:
    """Inside the window the frame shows both the caption and its backdrop."""
    frame = _frame(pinned_compiler, SAMPLE_T)
    alpha = frame.getchannel("A")
    assert alpha.getextrema()[1] == 255, "no fully opaque pixels (glyphs missing)"
    opaque = sum(alpha.histogram()[1:])
    assert opaque > 500, "frame is nearly empty"

    pixels = frame.load()
    box_pixels = glow_pixels = 0
    for y in range(0, frame.height, 4):
        for x in range(0, frame.width, 4):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if a > 100 and abs(r - 0x11) <= 12 and abs(g - 0x11) <= 12 and abs(b - 0x11) <= 12:
                box_pixels += 1
            if b > 180 and g > 150 and r < 90:
                glow_pixels += 1
    assert box_pixels > 50, "background box not rendered"
    assert glow_pixels > 10, "cyan glow not rendered"


def test_golden_frame_deterministic(pinned_compiler: Compiler) -> None:
    """Rendering the same frame twice yields identical bytes."""
    first = _frame(pinned_compiler, SAMPLE_T)
    second = _frame(pinned_compiler, SAMPLE_T)
    assert list(first.tobytes()) == list(second.tobytes())


def test_golden_uses_pinned_roboto() -> None:
    """The harness routes the renderer's font loads to the bundled file."""
    assert pinned.ROBOTO_PATH.is_file()
    face = pinned.pinned_font_manager().resolve(pinned.pinned_font_ref())
    assert face is not None and face.family == "Roboto"


def test_color_hex_parse_still_sane() -> None:
    """Sanity guard for the pixel probes above."""
    cyan = Color("#00E5FF")
    box = Color("#111111")
    assert (cyan.r, cyan.g, cyan.b) == (0, 229, 255)
    assert (box.r, box.g, box.b) == (17, 17, 17)
