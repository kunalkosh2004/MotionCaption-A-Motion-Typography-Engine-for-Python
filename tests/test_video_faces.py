"""Face detection adapter tests — detector and cv2 are faked."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

from motion_caption.errors import MissingDependencyError
from motion_caption.models import Box
from motion_caption.placement import Face
from motion_caption.video.faces import (
    OpenCVFaceDetector,
    _coalesce,
    _merge_nearby,
    _sample_times,
    detect_faces_for_video,
)


class _FakeDetector:
    def __init__(self, boxes: list[Box]) -> None:
        self.boxes = boxes
        self.calls = 0

    def detect(self, frame):
        self.calls += 1
        return self.boxes


class _FakeFFmpeg:
    def __init__(self, frame: Image.Image) -> None:
        self.frame = frame
        self.extractions: list[float] = []

    def extract_frame(self, video, time, output):
        self.extractions.append(time)
        target = Path(output)
        self.frame.save(target, format="PNG")
        return target


def _frame() -> Image.Image:
    image = Image.new("RGB", (64, 64), (10, 20, 30))
    ImageDraw_rect(image)
    return image


def ImageDraw_rect(image: Image.Image) -> None:
    from PIL import ImageDraw

    ImageDraw.Draw(image).rectangle((4, 4, 40, 40), fill=(200, 200, 200))


# --- sampling ---------------------------------------------------------------


def test_sample_times_with_duration() -> None:
    assert _sample_times(4, 3.0) == [0.0, 1.0, 2.0, 3.0]


def test_sample_times_without_duration() -> None:
    assert _sample_times(8, None) == [0.0]
    assert _sample_times(1, 5.0) == [0.0]


def test_sample_times_invalid() -> None:
    with pytest.raises(ValueError, match="samples"):
        detect_faces_for_video(_FakeFFmpeg(_frame()), _FakeDetector([]), "v.mp4", samples=0)


# --- video detection --------------------------------------------------------


def test_detect_faces_for_video_unions_across_samples(tmp_path) -> None:
    ffmpeg = _FakeFFmpeg(_frame())
    detector = _FakeDetector([Box(10, 10, 30, 30)])
    faces = detect_faces_for_video(
        ffmpeg, detector, tmp_path / "clip.mp4", samples=3, duration=2.0
    )
    assert len(ffmpeg.extractions) == 3
    assert detector.calls == 3
    assert all(isinstance(face, Face) for face in faces)
    assert faces[0].box.left == 10


def test_nearby_duplicates_are_merged() -> None:
    boxes = [Box(10, 10, 30, 30), Box(12, 11, 31, 32), Box(200, 200, 250, 250)]
    merged = _merge_nearby(boxes)
    assert len(merged) == 2


def test_coalesce_normalizes_flipped_box() -> None:
    face = _coalesce(Box(40, 50, 10, 20))
    assert (face.box.left, face.box.top, face.box.right, face.box.bottom) == (10, 20, 40, 50)


# --- OpenCV detector --------------------------------------------------------


class _FakeCascade:
    def __init__(self, detections) -> None:
        self.detections = detections

    def empty(self) -> bool:
        return False

    def detectMultiScale(self, gray, **kwargs):
        return self.detections


class _FakeCv2(ModuleType):
    def __init__(self) -> None:
        super().__init__("cv2")
        self.COLOR_RGB2GRAY = 0
        self.cascades: list[tuple[str, _FakeCascade]] = []

    def CascadeClassifier(self, path):
        cascade = _FakeCascade([(10, 20, 30, 40), (100, 100, 50, 60)])
        self.cascades.append((path, cascade))
        return cascade

    def cvtColor(self, rgb, code):
        return rgb


@pytest.fixture
def fake_cv2(monkeypatch):
    fake = _FakeCv2()
    monkeypatch.setitem(sys.modules, "cv2", fake)
    monkeypatch.setattr(
        "motion_caption.video.faces._default_cascade_path",
        lambda cv2: "/cascade.xml",
    )
    return fake


def test_opencv_detector_returns_boxes(fake_cv2) -> None:
    detector = OpenCVFaceDetector()
    boxes = detector.detect(Image.new("RGB", (200, 200), (0, 0, 0)))
    assert boxes == [Box(10.0, 20.0, 40.0, 60.0), Box(100.0, 100.0, 150.0, 160.0)]


def test_opencv_detector_cascade_missing(monkeypatch, fake_cv2) -> None:
    monkeypatch.setattr("motion_caption.video.faces._default_cascade_path", lambda cv2: "/none.xml")

    class _EmptyCascade:
        def empty(self) -> bool:
            return True

    fake_cv2.CascadeClassifier = lambda path: _EmptyCascade()
    detector = OpenCVFaceDetector()
    with pytest.raises(MissingDependencyError, match="failed to load") as exc_info:
        detector.detect(Image.new("RGB", (10, 10), (0, 0, 0)))
    assert exc_info.value.hint
