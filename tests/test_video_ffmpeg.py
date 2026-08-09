"""FFmpeg bridge tests — every subprocess call is mocked; no real ffmpeg."""

from __future__ import annotations

import json
import subprocess

import pytest

from motion_caption.errors import FFmpegError, InvalidVideoError
from motion_caption.video import FFmpegVideoProcessor, VideoMetadata, temporary_directory

FAKE_FFMPEG = "/usr/local/bin/ffmpeg"
FAKE_FFPROBE = "/usr/local/bin/ffprobe"


def _probe_json(*, width=1920, height=1080, fps="30/1", duration="10.0", audio=True) -> str:
    streams = [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": width,
            "height": height,
            "r_frame_rate": fps,
            "avg_frame_rate": fps,
            "duration": duration,
        }
    ]
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac", "duration": duration})
    return json.dumps({"format": {"duration": duration}, "streams": streams})


class _Result:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def processor() -> FFmpegVideoProcessor:
    return FFmpegVideoProcessor(ffmpeg_path=FAKE_FFMPEG, ffprobe_path=FAKE_FFPROBE)


def _patch_run(monkeypatch, *, stdout: str = "", stderr: str = "", returncode: int = 0):
    """Replace subprocess.run; record every argv so commands are assertable."""
    calls: list[list[str]] = []

    def _run(command, **kwargs):
        calls.append(command)
        return _Result(stdout=stdout, stderr=stderr, returncode=returncode)

    monkeypatch.setattr(subprocess, "run", _run)
    return calls


def test_available_false_when_binaries_missing(monkeypatch) -> None:
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.delenv("FFPROBE_PATH", raising=False)
    monkeypatch.setattr("motion_caption.video.ffmpeg.shutil.which", lambda _name: None)
    processor = FFmpegVideoProcessor(ffmpeg_path=None, ffprobe_path=None)
    assert processor.available() is False
    with pytest.raises(FFmpegError, match="ffmpeg executable not found"):
        processor.extract_audio("input.mp4")
    with pytest.raises(FFmpegError, match="ffprobe executable not found"):
        processor.probe("input.mp4")


def test_missing_input_file_raises_invalid_video(processor) -> None:
    with pytest.raises(InvalidVideoError, match="does not exist"):
        processor.probe("/no/such/file.mp4")


def test_probe_parses_metadata(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    calls = _patch_run(monkeypatch, stdout=_probe_json())
    metadata = processor.probe(video)
    assert isinstance(metadata, VideoMetadata)
    assert metadata.resolution == (1920, 1080)
    assert metadata.fps == 30.0
    assert metadata.duration == 10.0
    assert metadata.has_audio and metadata.has_video
    assert metadata.video_codec == "h264"
    # ffprobe was invoked with an argument array (never a shell string).
    assert calls[0][0] == FAKE_FFPROBE
    assert all(isinstance(arg, str) for arg in calls[0])


def test_probe_parses_rational_fps(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    _patch_run(monkeypatch, stdout=_probe_json(fps="30000/1001"))
    metadata = processor.probe(video)
    assert metadata.fps == pytest.approx(30000 / 1001)


def test_probe_no_video_stream_raises_invalid_video(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "audio_only.mp3"
    video.write_bytes(b"fake")
    _patch_run(monkeypatch, stdout=json.dumps({"streams": [{"codec_type": "audio"}]}))
    with pytest.raises(InvalidVideoError, match="no video stream"):
        processor.probe(video)


def test_probe_unparseable_output_raises_ffmpeg_error(
    processor, monkeypatch, tmp_path
) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    _patch_run(monkeypatch, stdout="not json at all")
    with pytest.raises(FFmpegError, match="unparseable"):
        processor.probe(video)


def test_probe_ffprobe_failure_raises_ffmpeg_error(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    _patch_run(monkeypatch, stderr="Invalid data found", returncode=1)
    with pytest.raises(FFmpegError, match="exit 1"):
        processor.probe(video)


def test_extract_audio_builds_wav_command(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    calls = _patch_run(monkeypatch)
    out = processor.extract_audio(video)
    command = calls[0]
    assert command[0] == FAKE_FFMPEG
    assert "-vn" in command
    assert "pcm_s16le" in command
    assert command[command.index("-ar") + 1] == "16000"
    assert command[-1] == str(video.with_suffix(".wav"))
    assert out == video.with_suffix(".wav")


def test_render_frames_to_video_builds_encoder_command(
    processor, monkeypatch, tmp_path
) -> None:
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "000000.png").write_bytes(b"x")
    calls = _patch_run(monkeypatch)
    out = processor.render_frames_to_video(
        frames, 30, tmp_path / "out.mp4", width=1080, height=1920
    )
    command = calls[0]
    assert command[0] == FAKE_FFMPEG
    assert command[command.index("-framerate") + 1] == "30"
    assert command[command.index("-i") + 1] == str(frames / "%06d.png")
    assert "libx264" in command and "yuv420p" in command
    assert command[-1] == str(tmp_path / "out.mp4")
    assert out == tmp_path / "out.mp4"


def test_render_frames_missing_dir_raises(processor) -> None:
    with pytest.raises(FFmpegError, match="frames directory not found"):
        processor.render_frames_to_video(
            "/no/frames/dir", 30, "out.mp4", width=640, height=360
        )


def test_mux_audio_maps_video_and_optional_audio(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "captioned.mp4"
    video.write_bytes(b"fake")
    calls = _patch_run(monkeypatch)
    processor.mux_audio(video, tmp_path / "original.mp4", tmp_path / "final.mp4")
    command = calls[0]
    assert command[command.index("-map") + 1] == "0:v"
    assert command[command.index("-map") + 1 + 2] == "1:a?"
    assert "-shortest" in command


def test_burn_subtitles_escapes_filter_path(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "clip with space.mp4"
    video.write_bytes(b"fake")
    ass = tmp_path / "sub file,1.ass"
    ass.write_text("[Script Info]", encoding="utf-8")
    calls = _patch_run(monkeypatch)
    processor.burn_subtitles(video, ass, tmp_path / "burned.mp4")
    command = calls[0]
    filter_arg = command[command.index("-vf") + 1]
    assert filter_arg.startswith("subtitles=")
    assert "sub file" in filter_arg  # spaces are fine inside an argv element
    assert "\\," in filter_arg  # the comma was escaped for the filter grammar


def test_timeout_raises_ffmpeg_error_with_hint(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    def _hang(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=1)

    monkeypatch.setattr(subprocess, "run", _hang)
    with pytest.raises(FFmpegError, match="timed out"):
        processor.extract_audio(video)


def test_command_failure_raises_ffmpeg_error(processor, monkeypatch, tmp_path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")
    _patch_run(monkeypatch, stderr="Conversion failed!", returncode=1)
    with pytest.raises(FFmpegError, match="exit 1") as exc_info:
        processor.extract_audio(video)
    assert exc_info.value.hint


def test_temporary_directory_cleans_up() -> None:
    with temporary_directory() as scratch:
        assert scratch.is_dir()
        marker = scratch / "keep.txt"
        marker.write_text("x", encoding="utf-8")
        assert marker.is_file()
    assert not scratch.exists()
