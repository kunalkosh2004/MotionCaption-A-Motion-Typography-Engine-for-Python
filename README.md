# MotionCaption

**Motion Typography Engine for Python.**

Deterministic, plugin-based animated subtitles for AI video editors. Turn a
word-timed transcript into professional captions with typography, emphasis,
and motion — rendered to ASS, FFmpeg filters, image sequences, and JSON
timelines.

> Not a subtitle generator. Not an AI project. An engine: the React / Pillow /
> OpenCV of subtitles.

## Status

Early development, built one subsystem at a time. Design contract lives in
[`docs/architecture.md`](docs/architecture.md).

Implemented so far:

- Core domain models (units, geometry, color, transcript, canvas, registry)
- Typography engine (font discovery, fallback, styles, measurement)

Up next: easing + keyframe engine, theme engine, segmentation, emphasis,
layout/placement, renderer, exporters.

## Install

```bash
pip install -e ".[dev]"    # development
pip install motion-caption # once published
```

Requires Python 3.12+.

## Example

```python
from motion_caption import CaptionEngine

engine = CaptionEngine(theme="music_video")
engine.render(transcript="words.json", output="captions.ass")
```
