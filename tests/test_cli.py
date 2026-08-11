"""CLI tests — run through ``main()`` with captured output; heavy backends faked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import motion_caption.cli as cli
from motion_caption.video import FakeTranscriptProvider
from motion_caption.video.ffmpeg import VideoMetadata

FAKE_METADATA = VideoMetadata(
    path=Path("in.mp4"),
    width=640,
    height=360,
    fps=30.0,
    duration=2.0,
    has_audio=True,
    has_video=True,
    video_codec="h264",
    audio_codec="aac",
)


def _run(argv, capsys) -> int:
    code = cli.main(argv)
    return code


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])
    assert exc_info.value.code == 0


def test_no_command_is_usage_error(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_themes_lists_builtins(capsys) -> None:
    assert _run(["themes"], capsys) == 0
    out = capsys.readouterr().out
    assert "themes" in out
    for theme in ("clean", "music_video", "cinematic"):
        assert theme in out


def test_animations_lists_templates(capsys) -> None:
    assert _run(["animations"], capsys) == 0
    out = capsys.readouterr().out
    assert "animations" in out
    assert "karaoke" in out


def test_exporters_lists_backends(capsys) -> None:
    assert _run(["exporters"], capsys) == 0
    out = capsys.readouterr().out
    assert "ass" in out and "json" in out


def _write_request(tmp_path: Path) -> Path:
    request = {
        "transcript": {
            "words": [
                {"text": "hello", "start": 0.0, "end": 0.5},
                {"text": "world", "start": 0.5, "end": 1.0},
            ]
        },
        "theme": "clean",
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    return path


def test_compile_command(tmp_path, capsys) -> None:
    request = _write_request(tmp_path)
    output = tmp_path / "timeline.json"
    assert _run(["compile", str(request), "-o", str(output)], capsys) == 0
    assert "compiled" in capsys.readouterr().out
    timeline = json.loads(output.read_text(encoding="utf-8"))
    assert timeline["format_version"] == "1.0"
    assert sum(len(track["events"]) for track in timeline["tracks"]) >= 1


def test_compile_missing_file_is_human_error(tmp_path, capsys) -> None:
    code = _run(["compile", str(tmp_path / "missing.json")], capsys)
    assert code == 1
    err = capsys.readouterr().err
    assert "error:" in err


def test_export_ass_command(tmp_path, capsys) -> None:
    request = _write_request(tmp_path)
    timeline = tmp_path / "timeline.json"
    cli.main(["compile", str(request), "-o", str(timeline)])
    out = tmp_path / "captions.ass"
    code = _run(["export", str(timeline), "--format", "ass", "-o", str(out)], capsys)
    assert code == 0
    assert "Dialogue:" in out.read_text(encoding="utf-8")


def test_render_command(tmp_path, capsys) -> None:
    request = _write_request(tmp_path)
    timeline = tmp_path / "timeline.json"
    cli.main(["compile", str(request), "-o", str(timeline)])
    frames = tmp_path / "frames"
    code = _run(["render", str(timeline), "--fps", "10", "-o", str(frames)], capsys)
    assert code == 0
    pngs = list(frames.glob("*.png"))
    assert pngs, "render must produce PNG frames"
    assert "rendered" in capsys.readouterr().out


def test_info_command_uses_ffprobe(monkeypatch, tmp_path, capsys) -> None:
    calls: list[str] = []

    class _FakeProcessor:
        def probe(self, path):
            calls.append(str(path))
            return FAKE_METADATA

    monkeypatch.setattr(cli, "FFmpegVideoProcessor", _FakeProcessor)
    video = tmp_path / "in.mp4"
    video.write_bytes(b"x")
    code = _run(["info", str(video)], capsys)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["resolution"] == "640x360"
    assert payload["has_audio"] is True
    assert calls == [str(video)]


def test_caption_command_wires_pipeline(monkeypatch, tmp_path, capsys) -> None:
    from motion_caption.video.pipeline import PipelineResult

    captured: dict = {}

    class _FakePipeline:
        def __init__(self, **kwargs) -> None:
            captured["kwargs"] = kwargs

        def process(self, input_video, output_video=None, **kwargs):
            captured["input"] = str(input_video)
            captured["output"] = output_video
            captured["process_kwargs"] = kwargs
            return PipelineResult(
                output_video=Path("out.mp4"),
                timeline=None,  # type: ignore[arg-type]
                transcript=None,  # type: ignore[arg-type]
                metadata=FAKE_METADATA,
                event_count=2,
                word_count=4,
                frames_rendered=60,
                llm_annotated=False,
                theme="clean",
            )

    monkeypatch.setattr(cli, "CaptionVideoPipeline", _FakePipeline)
    video = tmp_path / "in.mp4"
    video.write_bytes(b"x")
    code = _run(
        [
            "caption",
            str(video),
            "--theme",
            "music_video",
            "--preset",
            "youtube_shorts",
            "--fps",
            "24",
            "-o",
            "out.mp4",
        ],
        capsys,
    )
    assert code == 0
    assert captured["kwargs"]["preset"] == "youtube_shorts"
    assert captured["kwargs"]["theme"] == "music_video"
    assert captured["kwargs"]["fps"] == 24
    assert captured["input"] == str(video)
    assert captured["output"] == "out.mp4"
    assert "captioned" in capsys.readouterr().out


def test_caption_theme_defaults_to_auto(monkeypatch, tmp_path, capsys) -> None:
    from motion_caption.video.pipeline import PipelineResult

    captured: dict = {}

    class _FakePipeline:
        def __init__(self, **kwargs) -> None:
            captured["kwargs"] = kwargs

        def process(self, input_video, output_video=None, **kwargs):
            return PipelineResult(
                output_video=Path("out.mp4"),
                timeline=None,  # type: ignore[arg-type]
                transcript=None,  # type: ignore[arg-type]
                metadata=FAKE_METADATA,
                event_count=1,
                word_count=2,
                frames_rendered=30,
                llm_annotated=False,
                theme="sport",
            )

    monkeypatch.setattr(cli, "CaptionVideoPipeline", _FakePipeline)
    video = tmp_path / "in.mp4"
    video.write_bytes(b"x")
    code = _run(["caption", str(video)], capsys)
    assert code == 0
    assert captured["kwargs"]["theme"] is None
    assert "theme: sport" in capsys.readouterr().out


def test_caption_command_with_transcript_file(tmp_path, capsys, monkeypatch) -> None:
    from motion_caption.video.pipeline import PipelineResult

    transcript = FakeTranscriptProvider("hello cli").transcribe("x.wav")
    transcript_path = tmp_path / "transcript.json"
    transcript_path.write_text(transcript.model_dump_json(), encoding="utf-8")

    class _FakePipeline:
        def __init__(self, **kwargs) -> None:
            pass

        def process(self, input_video, output_video=None, **kwargs):
            assert kwargs["transcript"].word_count == 2
            return PipelineResult(
                output_video=Path("out.mp4"),
                timeline=None,  # type: ignore[arg-type]
                transcript=kwargs["transcript"],
                metadata=FAKE_METADATA,
                event_count=1,
                word_count=2,
                frames_rendered=30,
                llm_annotated=False,
                theme="clean",
            )

    monkeypatch.setattr(cli, "CaptionVideoPipeline", _FakePipeline)
    video = tmp_path / "in.mp4"
    video.write_bytes(b"x")
    code = _run(
        ["caption", str(video), "--transcript", str(transcript_path), "-o", "out.mp4"],
        capsys,
    )
    assert code == 0


def test_caption_command_with_transcript_provider(monkeypatch, tmp_path, capsys) -> None:
    from motion_caption.video.gemini import GeminiTranscriptProvider
    from motion_caption.video.pipeline import PipelineResult

    captured: dict = {}

    class _FakePipeline:
        def __init__(self, **kwargs) -> None:
            captured["provider"] = kwargs.get("transcript_provider")

        def process(self, input_video, output_video=None, **kwargs):
            return PipelineResult(
                output_video=Path("out.mp4"),
                timeline=None,  # type: ignore[arg-type]
                transcript=None,  # type: ignore[arg-type]
                metadata=FAKE_METADATA,
                event_count=1,
                word_count=2,
                frames_rendered=30,
                llm_annotated=False,
                theme="clean",
            )

    monkeypatch.setattr(cli, "CaptionVideoPipeline", _FakePipeline)
    video = tmp_path / "in.mp4"
    video.write_bytes(b"x")
    code = _run(["caption", str(video), "--transcript-provider", "gemini"], capsys)
    assert code == 0
    assert isinstance(captured["provider"], GeminiTranscriptProvider)


def test_caption_ai_error_prints_hint(monkeypatch, tmp_path, capsys) -> None:
    from motion_caption.errors import AIProviderError

    class _RaisingPipeline:
        def __init__(self, **kwargs) -> None:
            pass

        def process(self, *args, **kwargs):
            raise AIProviderError(
                "unknown AI provider 'bogus'", hint="available: gemini, openai"
            )

    monkeypatch.setattr(cli, "CaptionVideoPipeline", _RaisingPipeline)
    video = tmp_path / "in.mp4"
    video.write_bytes(b"x")
    code = _run(["caption", str(video), "--ai", "bogus", "-o", "out.mp4"], capsys)
    assert code == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "available: gemini, openai" in err  # the hint is surfaced


def test_invalid_resolution_is_human_error(tmp_path, capsys) -> None:
    request = _write_request(tmp_path)
    timeline = tmp_path / "timeline.json"
    cli.main(["compile", str(request), "-o", str(timeline)])
    code = _run(["render", str(timeline), "--resolution", "garbage"], capsys)
    assert code == 1
    assert "error:" in capsys.readouterr().err
