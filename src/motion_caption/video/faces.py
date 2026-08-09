"""Optional face detection for face-aware caption placement.

The compiler never calls a detector — placement consumes normalized ``Face``
boxes (``CaptionRequest.faces``) that the application layer supplies. This
module provides:

* ``FaceDetector`` — the seam any provider (YOLO, RetinaFace, MediaPipe,
  OpenCV, ...) can implement.
* ``OpenCVFaceDetector`` — a zero-download Haar-cascade detector (OpenCV is
  already a declared dependency) operating on Pillow RGBA frames.
* ``detect_faces_for_video`` — a sampling strategy: run detection on a handful
  of frames spread across the video and return the *union* of all face boxes,
  so captions avoid everywhere a face ever appears. Full per-frame detection
  is deliberately not done (cost); the union is a conservative, safe zone.

Detector output is pixel-space boxes on the sampled frame, which equals the
video resolution — the same space ``CaptionRequest.faces`` expects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from motion_caption.errors import MissingDependencyError
from motion_caption.models import Box
from motion_caption.placement import Face
from motion_caption.video.ffmpeg import FFmpegVideoProcessor, temporary_directory


class FaceDetector(Protocol):
    """Anything that finds faces in a single Pillow RGBA frame."""

    def detect(self, frame) -> list[Box]:
        """Return pixel-space face boxes for one frame (Pillow ``Image``)."""
        ...


class OpenCVFaceDetector:
    """Haar-cascade face detection through OpenCV (lazy import).

    ``cascade_path`` may point at a bundled ``haarcascade_frontalface_default``
    XML; when ``None`` the detector falls back to OpenCV's data directory.
    """

    name = "opencv-haar"

    def __init__(self, cascade_path: str | Path | None = None) -> None:
        self.cascade_path = str(cascade_path) if cascade_path else None
        self._cascade = None

    def _load_cascade(self):
        if self._cascade is not None:
            return self._cascade
        cv2 = _require_cv2()
        path = self.cascade_path or _default_cascade_path(cv2)
        cascade = cv2.CascadeClassifier(path)
        if cascade.empty():
            raise MissingDependencyError(
                f"failed to load Haar cascade from {path}",
                hint="pass cascade_path= or reinstall opencv-python-headless",
            )
        self._cascade = cascade
        return cascade

    def detect(self, frame) -> list[Box]:
        cv2 = _require_cv2()
        import numpy as np

        rgb = np.asarray(frame.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        faces = self._load_cascade().detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
        )
        return [Box(float(x), float(y), float(x + w), float(y + h)) for x, y, w, h in faces]


def _require_cv2():
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise MissingDependencyError(
            "OpenCV (cv2) is not installed",
            hint="pip install 'motion-caption[video]' (or pip install opencv-python-headless)",
        ) from exc
    return cv2


def _default_cascade_path(cv2) -> str:
    """Locate OpenCV's bundled frontal-face Haar cascade."""
    data_dir = Path(cv2.__file__).parent / "data"
    for candidate in data_dir.glob("haarcascade_frontalface_default.xml"):
        return str(candidate)
    raise RuntimeError(
        "no bundled Haar cascade found; pass cascade_path=",
    )


def detect_faces_for_video(
    ffmpeg: FFmpegVideoProcessor,
    detector: FaceDetector,
    video_path: str | Path,
    *,
    samples: int = 8,
    duration: float | None = None,
) -> list[Face]:
    """Detect faces on ``samples`` frames spread across the video.

    Returns the union of every detected box as ``Face`` objects. ``duration``
    may come from ``probe()``; when omitted the detector returns faces for a
    single frame at ``t=0``.
    """
    if samples < 1:
        raise ValueError(f"samples must be >= 1, got {samples}")
    if duration is not None and duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    times = _sample_times(samples, duration)
    union: list[Box] = []
    with temporary_directory() as scratch:
        for index, time in enumerate(times):
            frame_path = scratch / f"sample-{index:04d}.png"
            ffmpeg.extract_frame(video_path, time, frame_path)
            from PIL import Image

            frame = Image.open(frame_path).convert("RGBA")
            union.extend(detector.detect(frame))
    return [_coalesce(box) for box in _merge_nearby(union)]


def _sample_times(samples: int, duration: float | None) -> list[float]:
    if duration is None:
        return [0.0]
    if samples == 1:
        return [0.0]
    step = duration / (samples - 1)
    return [round(step * index, 3) for index in range(samples)]


def _merge_nearby(boxes: list[Box], tolerance: float = 24.0) -> list[Box]:
    """Drop near-duplicate detections (cascades over-fire per face)."""
    merged: list[Box] = []
    for box in boxes:
        if any(_close(box, existing, tolerance) for existing in merged):
            continue
        merged.append(box)
    return merged


def _close(a: Box, b: Box, tolerance: float) -> bool:
    return (
        abs(a.left - b.left) < tolerance
        and abs(a.top - b.top) < tolerance
        and abs(a.right - b.right) < tolerance
        and abs(a.bottom - b.bottom) < tolerance
    )


def _coalesce(box: Box) -> Face:
    """Sanitize a detector box into a ``Face`` for the compiler."""
    left = min(box.left, box.right)
    right = max(box.left, box.right)
    top = min(box.top, box.bottom)
    bottom = max(box.top, box.bottom)
    return Face(box=Box(left, top, right, bottom))
