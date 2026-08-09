"""JSON file IO tests for requests, transcripts and timelines."""

from __future__ import annotations

import json

import pytest

from motion_caption.errors import InvalidTranscriptError, RequestIOError
from motion_caption.io import (
    load_request,
    load_timeline,
    load_transcript,
    save_request,
    save_timeline,
)
from motion_caption.ir.request import CaptionRequest
from motion_caption.models import Transcript, WordTimestamp
from motion_caption.video import FakeTranscriptProvider

MINIMAL_REQUEST_JSON = """
{
  "transcript": {"words": [{"text": "hello", "start": 0.0, "end": 0.5}]},
  "theme": "music_video",
  "platform": "youtube_shorts"
}
"""


def test_request_round_trip(tmp_path) -> None:
    path = tmp_path / "request.json"
    request = CaptionRequest(
        transcript=Transcript(words=[WordTimestamp(text="hello", start=0.0, end=0.5)]),
        theme="music_video",
        platform="youtube_shorts",
    )
    save_request(request, path)
    loaded = load_request(path)
    assert loaded == request
    assert loaded.theme == "music_video"
    assert loaded.platform == "youtube_shorts"


def test_load_request_from_minimal_json(tmp_path) -> None:
    path = tmp_path / "req.json"
    path.write_text(MINIMAL_REQUEST_JSON, encoding="utf-8")
    request = load_request(path)
    assert request.transcript.words[0].text == "hello"
    assert request.theme == "music_video"
    assert request.resolved_resolution.width == 1920  # default


def test_load_request_compiles(tmp_path) -> None:
    path = tmp_path / "req.json"
    path.write_text(MINIMAL_REQUEST_JSON, encoding="utf-8")
    from motion_caption.compiler import compile

    timeline = compile(load_request(path))
    assert len(timeline.events) >= 1


def test_load_request_missing_file(tmp_path) -> None:
    with pytest.raises(RequestIOError, match="cannot read"):
        load_request(tmp_path / "nope.json")


def test_load_request_invalid_json(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RequestIOError, match="invalid CaptionRequest"):
        load_request(path)


def test_load_request_wrong_shape(tmp_path) -> None:
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"transcript": "oops"}), encoding="utf-8")
    with pytest.raises(RequestIOError, match="invalid CaptionRequest") as exc_info:
        load_request(path)
    assert exc_info.value.hint  # actionable pydantic detail


def test_transcript_round_trip_and_validation(tmp_path) -> None:
    path = tmp_path / "transcript.json"
    transcript = FakeTranscriptProvider("hello caption world").transcribe("x.wav")
    path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    loaded = load_transcript(path)
    assert loaded.word_count == 3


def test_load_transcript_invalid_raises_transcript_error(tmp_path) -> None:
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"words": "nope"}), encoding="utf-8")
    with pytest.raises(InvalidTranscriptError, match="invalid transcript"):
        load_transcript(path)


def test_timeline_round_trip(tmp_path) -> None:
    from motion_caption.compiler import compile

    timeline = compile(_request_with(FakeTranscriptProvider("hello world").transcribe("x")))
    path = tmp_path / "timeline.json"
    save_timeline(timeline, path)
    loaded = load_timeline(path)
    assert loaded.format_version == timeline.format_version
    assert len(loaded.events) == len(timeline.events)
    assert loaded.model_dump_json() == timeline.model_dump_json()


def test_save_writes_nested_directories(tmp_path) -> None:
    path = tmp_path / "a" / "b" / "c" / "req.json"
    request = _request_with(Transcript(words=[WordTimestamp(text="x", start=0.0, end=1.0)]))
    save_request(request, path)
    assert path.is_file()


def _request_with(transcript: Transcript) -> CaptionRequest:
    return CaptionRequest(transcript=transcript, theme="clean")
