"""``motion-caption`` command line interface.

A thin application shell over the library — it never reimplements compiler
logic. Commands:

    motion-caption caption input.mp4 --theme music_video --preset youtube_shorts -o out.mp4
    motion-caption compile request.json -o timeline.json
    motion-caption render timeline.json --fps 30 -o frames/
    motion-caption export timeline.json --format ass -o captions.ass
    motion-caption themes | animations | exporters
    motion-caption info input.mp4

All failures are human-readable: ``error: <what> (<how to fix>)`` on stderr
with exit code 1; usage errors exit 2. The handlers raise the library's typed
errors, so the same code paths stay usable programmatically.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from motion_caption import __version__
from motion_caption.animations import ANIMATION_REGISTRY
from motion_caption.canvas import Canvas
from motion_caption.compiler import compile
from motion_caption.errors import MotionCaptionError
from motion_caption.exporters import EXPORTER_REGISTRY
from motion_caption.io import load_request, load_timeline
from motion_caption.render import TimelineRenderer
from motion_caption.themes import THEME_REGISTRY
from motion_caption.video import CaptionVideoPipeline
from motion_caption.video.ffmpeg import FFmpegVideoProcessor

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="motion-caption",
        description="MotionCaption — deterministic motion typography for video.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # caption ---------------------------------------------------------------
    caption = subparsers.add_parser(
        "caption", help="caption a video end-to-end (transcribe → compile → render → mux)"
    )
    caption.add_argument("input", help="input video file")
    caption.add_argument("-o", "--output", help="output video (default: <input>_captioned.mp4)")
    caption.add_argument("--theme", default="clean", help="theme name (default: clean)")
    caption.add_argument(
        "--preset",
        "--platform",
        dest="preset",
        default=None,
        help="platform preset: youtube_shorts, tiktok, instagram_reels, "
        "youtube_landscape, square",
    )
    caption.add_argument(
        "--ai",
        dest="ai",
        metavar="PROVIDER",
        default=None,
        help="annotate with an AI provider first (gemini, openai); needs an API key",
    )
    caption.add_argument(
        "--transcript", help="skip transcription; read a Transcript JSON file instead"
    )
    caption.add_argument("--fps", type=int, default=None, help="frame rate (default 30)")
    caption.add_argument(
        "--resolution", default=None, help="output resolution WxH (default: input size)"
    )
    caption.set_defaults(handler=_cmd_caption)

    # compile ---------------------------------------------------------------
    compile_parser = subparsers.add_parser(
        "compile", help="compile a CaptionRequest JSON into a SubtitleTimeline JSON"
    )
    compile_parser.add_argument("request", help="CaptionRequest JSON file")
    compile_parser.add_argument("-o", "--output", default="timeline.json")
    compile_parser.set_defaults(handler=_cmd_compile)

    # render ----------------------------------------------------------------
    render_parser = subparsers.add_parser(
        "render", help="rasterize a SubtitleTimeline JSON into a PNG frame sequence"
    )
    render_parser.add_argument("timeline", help="SubtitleTimeline JSON file")
    render_parser.add_argument("-o", "--output", default="frames/", help="output directory")
    render_parser.add_argument("--resolution", default=None, help="override WxH")
    render_parser.add_argument("--fps", type=int, default=30)
    render_parser.set_defaults(handler=_cmd_render)

    # export ----------------------------------------------------------------
    export_parser = subparsers.add_parser(
        "export", help="export a SubtitleTimeline JSON through a backend (ass, json)"
    )
    export_parser.add_argument("timeline", help="SubtitleTimeline JSON file")
    export_parser.add_argument("--format", choices=("ass", "json"), default="ass")
    export_parser.add_argument("-o", "--output", default=None, help="output file")
    export_parser.set_defaults(handler=_cmd_export)

    # listing commands ------------------------------------------------------
    subparsers.add_parser("themes", help="list built-in themes").set_defaults(
        handler=_cmd_themes
    )
    subparsers.add_parser("animations", help="list animation templates").set_defaults(
        handler=_cmd_animations
    )
    subparsers.add_parser("exporters", help="list exporter backends").set_defaults(
        handler=_cmd_exporters
    )

    # info ------------------------------------------------------------------
    info = subparsers.add_parser("info", help="inspect a media file with ffprobe")
    info.add_argument("input", help="input video file")
    info.set_defaults(handler=_cmd_info)

    return parser


# -- handlers ----------------------------------------------------------------


def _parse_resolution(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    try:
        width, height = value.lower().split("x")
        return (int(width), int(height))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid resolution {value!r}; use WxH (e.g. 1080x1920)") from exc


def _cmd_caption(args: argparse.Namespace) -> None:
    transcript = load_transcript_file(args.transcript) if args.transcript else None
    pipeline = CaptionVideoPipeline(
        theme=args.theme,
        preset=args.preset,
        resolution=_parse_resolution(args.resolution),
        ai_provider=args.ai,
        fps=args.fps,
    )
    result = pipeline.process(
        args.input,
        args.output,
        transcript=transcript,
    )
    print(
        f"captioned {args.input} -> {result.output_video} "
        f"({result.event_count} events, {result.word_count} words, "
        f"{result.frames_rendered} frames"
        + (", AI-annotated" if result.llm_annotated else "")
        + ")"
    )


def _cmd_compile(args: argparse.Namespace) -> None:
    timeline = compile(load_request(args.request))
    from motion_caption.io import save_timeline

    save_timeline(timeline, args.output)
    print(f"compiled {args.request} -> {args.output} ({len(timeline.events)} events)")


def _cmd_render(args: argparse.Namespace) -> None:
    timeline = load_timeline(args.timeline)
    resolution = _parse_resolution(args.resolution)
    if resolution is not None:
        canvas = Canvas(width=resolution[0], height=resolution[1])
        scale = canvas.width / timeline.resolution.width
    else:
        canvas = Canvas(width=timeline.resolution.width, height=timeline.resolution.height)
        scale = None
    out = TimelineRenderer().render_sequence_to_directory(
        timeline,
        canvas,
        args.output,
        fps=args.fps,
        scale=scale,
    )
    frames = len(list(out.glob("*.png")))
    print(f"rendered {frames} frames -> {out}")


def _cmd_export(args: argparse.Namespace) -> None:
    timeline = load_timeline(args.timeline)
    exporter = EXPORTER_REGISTRY.get(args.format)
    result = exporter.export(timeline)
    output = Path(args.output) if args.output else Path(args.timeline).with_suffix(
        f".{result.extension}"
    )
    data = result.data
    if isinstance(data, str):
        output.write_text(data, encoding="utf-8")
    else:
        output.write_bytes(data)
    print(f"exported {args.format} -> {output}")


def _cmd_themes(args: argparse.Namespace) -> None:
    _print_listing("themes", sorted(THEME_REGISTRY.keys))


def _cmd_animations(args: argparse.Namespace) -> None:
    _print_listing("animations", sorted(ANIMATION_REGISTRY.keys))


def _cmd_exporters(args: argparse.Namespace) -> None:
    _print_listing("exporters", sorted(EXPORTER_REGISTRY.keys))


def _cmd_info(args: argparse.Namespace) -> None:
    metadata = FFmpegVideoProcessor().probe(args.input)
    info = {
        "path": str(metadata.path),
        "resolution": f"{metadata.width}x{metadata.height}",
        "fps": round(metadata.fps, 3),
        "duration": round(metadata.duration, 3),
        "video_codec": metadata.video_codec,
        "audio_codec": metadata.audio_codec,
        "has_audio": metadata.has_audio,
    }
    print(json.dumps(info, indent=2))


def _print_listing(kind: str, names: list[str]) -> None:
    print(f"{kind} ({len(names)}):")
    for name in names:
        print(f"  {name}")


def load_transcript_file(path: str) -> Any:
    from motion_caption.io import load_transcript

    return load_transcript(path)


# -- entry point -------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns a process exit code (never raises)."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        args.handler(args)
        return EXIT_OK
    except SystemExit as exc:  # --help / --version / usage errors
        raise exc
    except MotionCaptionError as exc:
        hint = f" ({exc.hint})" if exc.hint else ""
        print(f"error: {exc.message}{hint}", file=sys.stderr)
        return EXIT_ERROR
    except (ValueError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
