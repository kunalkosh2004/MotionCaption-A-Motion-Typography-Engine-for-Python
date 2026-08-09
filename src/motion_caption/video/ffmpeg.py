"""FFmpeg bridge for the application video layer.

This module is strictly an *integration* seam — it knows nothing about
``SubtitleTimeline``, themes, animation or the compiler. It wraps the
``ffmpeg`` / ``ffprobe`` executables with argument-array ``subprocess`` calls
(no shell string concatenation, so paths with spaces and special characters
are safe), timeouts, and typed errors.

Every command goes through ``FFmpegVideoProcessor._run`` which:

* checks the binary exists (``FFMPEG_PATH`` env or ``PATH``),
* enforces a timeout,
* raises ``FFmpegError`` with the failing command and a tail of stderr, or
  ``InvalidVideoError`` when the input is not a usable media file.

Temporary directories are the caller's responsibility for long-lived jobs;
``temporary_directory()`` provides a reliable, always-cleaned scratch dir.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from motion_caption.errors import FFmpegError, InvalidVideoError

_DEFAULT_TIMEOUT = 120.0


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """Snapshot of a probed media file (numbers only; no pixel data)."""

    path: Path
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool
    has_video: bool
    video_codec: str | None = None
    audio_codec: str | None = None

    @property
    def resolution(self) -> tuple[int, int]:
        return (self.width, self.height)


@dataclass(slots=True)
class _StreamInfo:
    codec_type: str = ""
    codec_name: str | None = None
    width: int | None = None
    height: int | None = None
    r_frame_rate: str | None = None
    avg_frame_rate: str | None = None
    duration: str | None = None


def _parse_rate(value: str | None, fallback: float) -> float:
    """Parse an ffprobe frame-rate string (\"30000/1001\") into a float."""
    if not value:
        return fallback
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            return float(numerator) / float(denominator)
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return fallback


def _parse_duration(value: str | None, fallback: float) -> float:
    if not value:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def temporary_directory(prefix: str = "motioncaption-") -> contextlib.AbstractContextManager[Path]:
    """A scratch directory that is always removed (even on exceptions)."""

    @contextlib.contextmanager
    def _manager() -> object:
        path = Path(tempfile.mkdtemp(prefix=prefix))
        try:
            yield path
        finally:
            shutil.rmtree(path, ignore_errors=True)

    return _manager()


class FFmpegVideoProcessor:
    """Thin, typed wrapper over the ``ffmpeg`` / ``ffprobe`` executables.

    Binary resolution order: explicit argument → ``FFMPEG_PATH`` /
    ``FFPROBE_PATH`` env vars → ``PATH``. Constructing the processor never
    raises; calling a method on a machine without FFmpeg raises
    ``FFmpegError`` with an install hint.
    """

    def __init__(
        self,
        ffmpeg_path: str | None = None,
        ffprobe_path: str | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.ffmpeg = ffmpeg_path or os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
        self.ffprobe = (
            ffprobe_path or os.environ.get("FFPROBE_PATH") or shutil.which("ffprobe")
        )
        self.timeout = timeout

    # -- presence ------------------------------------------------------------

    def available(self) -> bool:
        """True when both executables resolve."""
        return bool(self.ffmpeg and self.ffprobe)

    def _require_ffmpeg(self) -> str:
        if not self.ffmpeg:
            raise FFmpegError(
                "ffmpeg executable not found",
                hint="install ffmpeg (brew install ffmpeg) or set FFMPEG_PATH",
            )
        return self.ffmpeg

    def _require_ffprobe(self) -> str:
        if not self.ffprobe:
            raise FFmpegError(
                "ffprobe executable not found",
                hint="install ffmpeg (brew install ffmpeg) or set FFPROBE_PATH",
            )
        return self.ffprobe

    # -- core runner ---------------------------------------------------------

    def _run(
        self,
        command: list[str],
        *,
        check_file: Path | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run an argument-array command; raise typed errors on failure."""
        if check_file is not None and not check_file.is_file():
            raise InvalidVideoError(
                f"input file does not exist: {check_file}",
                hint="check the path is correct and the file is readable",
            )
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise FFmpegError(
                f"command timed out after {timeout or self.timeout:g}s: {' '.join(command)}",
                hint="increase the timeout or shorten the media",
            ) from exc
        except OSError as exc:
            raise FFmpegError(
                f"failed to start {' '.join(command)}: {exc}",
                hint="check the binary path resolves and is executable",
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()[-3:]
            raise FFmpegError(
                f"command failed (exit {result.returncode}): {' '.join(command)}",
                hint="; ".join(detail) or "see ffmpeg stderr for details",
            )
        return result

    # -- metadata ------------------------------------------------------------

    def probe(self, video_path: str | Path) -> VideoMetadata:
        """Inspect a media file and return its structural metadata."""
        source = Path(video_path)
        self._require_ffprobe()
        if not source.is_file():
            raise InvalidVideoError(
                f"input file does not exist: {source}",
                hint="check the path is correct and the file is readable",
            )
        result = self._run(
            [
                self._require_ffprobe(),
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(source),
            ]
        )
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise FFmpegError(
                f"ffprobe returned unparseable output for {source}",
                hint="the file may be corrupt or an unsupported container",
            ) from exc

        streams = [
            _StreamInfo(
                codec_type=str(s.get("codec_type") or ""),
                codec_name=s.get("codec_name"),
                width=s.get("width"),
                height=s.get("height"),
                r_frame_rate=s.get("r_frame_rate"),
                avg_frame_rate=s.get("avg_frame_rate"),
                duration=s.get("duration"),
            )
            for s in payload.get("streams") or []
        ]
        video_streams = [s for s in streams if s.codec_type == "video"]
        audio_streams = [s for s in streams if s.codec_type == "audio"]
        if not video_streams:
            raise InvalidVideoError(
                f"no video stream found in {source}",
                hint="this file is not a decodable video (check with: ffprobe <file>)",
            )
        video = video_streams[0]
        fmt = payload.get("format") or {}
        duration = _parse_duration(
            fmt.get("duration") or video.duration, fallback=0.0
        )
        fps = _parse_rate(video.r_frame_rate, fallback=30.0)
        return VideoMetadata(
            path=source,
            width=int(video.width or 0),
            height=int(video.height or 0),
            fps=fps,
            duration=duration,
            has_audio=bool(audio_streams),
            has_video=True,
            video_codec=video.codec_name,
            audio_codec=audio_streams[0].codec_name if audio_streams else None,
        )

    # -- audio ---------------------------------------------------------------

    def extract_audio(
        self,
        video_path: str | Path,
        output: str | Path | None = None,
        *,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> Path:
        """Extract a transcription-ready WAV (16 kHz mono by default).

        WhisperX consumes mono 16 kHz audio; the pipeline uses this as the
        transcript source. Pass ``output=`` to control the destination.
        """
        source = Path(video_path)
        target = Path(output) if output else source.with_suffix(".wav")
        self._run(
            [
                self._require_ffmpeg(),
                "-y",
                "-i",
                str(source),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                str(sample_rate),
                "-ac",
                str(channels),
                str(target),
            ],
            check_file=source,
        )
        return target

    # -- frame extraction ----------------------------------------------------

    def extract_frame(
        self,
        video_path: str | Path,
        time: float,
        output: str | Path,
    ) -> Path:
        """Extract a single frame at ``time`` seconds to a PNG.

        Used for sampling-based face detection and preview frames; the seek is
        done by decode time (``-ss`` before the input) so it is fast.
        """
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                self._require_ffmpeg(),
                "-y",
                "-ss",
                f"{max(0.0, time):g}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(target),
            ],
            check_file=Path(video_path),
        )
        return target

    # -- frames → video ------------------------------------------------------

    def render_frames_to_video(
        self,
        frames_dir: str | Path,
        fps: float,
        output: str | Path,
        *,
        width: int,
        height: int,
        pattern: str = "%06d.png",
        crf: int = 18,
    ) -> Path:
        """Encode a zero-indexed PNG sequence into H.264 MP4.

        ``frames_dir`` must contain ``000000.png, 000001.png, ...`` (the
        pattern used by ``TimelineRenderer.render_sequence``). The encoder
        pads to the declared canvas and uses yuv420p so the result plays
        everywhere (browsers, social platforms).
        """
        frames = Path(frames_dir)
        if not frames.is_dir():
            raise FFmpegError(
                f"frames directory not found: {frames}",
                hint="render the frame sequence before encoding",
            )
        target = Path(output)
        self._run(
            [
                self._require_ffmpeg(),
                "-y",
                "-framerate",
                f"{fps:g}",
                "-i",
                str(frames / pattern),
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                str(crf),
                "-movflags",
                "+faststart",
                str(target),
            ]
        )
        return target

    # -- audio muxing --------------------------------------------------------

    def mux_audio(
        self,
        video_path: str | Path,
        audio_source: str | Path,
        output: str | Path,
    ) -> Path:
        """Mux the audio track of ``audio_source`` onto a silent captioned video.

        ``audio_source`` may be an audio file *or* the original video — ffmpeg
        maps its first audio stream (``-map 1:a?``), so passing the original
        MP4 preserves full-quality audio. Streams are copied, never re-encoded.
        """
        target = Path(output)
        self._run(
            [
                self._require_ffmpeg(),
                "-y",
                "-i",
                str(video_path),
                "-i",
                str(audio_source),
                "-map",
                "0:v",
                "-map",
                "1:a?",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-shortest",
                str(target),
            ],
            check_file=Path(video_path),
        )
        return target

    # -- ASS burning ---------------------------------------------------------

    def burn_subtitles(
        self,
        video_path: str | Path,
        ass_path: str | Path,
        output: str | Path,
    ) -> Path:
        """Burn an ASS file into the frames (``subtitles`` filter).

        The ASS path is embedded in an ffmpeg *filter* string, where ``:``,
        ``\\``, ``'`` and ``,`` are syntax — escape them so spaces and special
        characters in the path cannot break the command.
        """
        escaped = _escape_filter_path(str(ass_path))
        target = Path(output)
        self._run(
            [
                self._require_ffmpeg(),
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"subtitles={escaped}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(target),
            ],
            check_file=Path(video_path),
        )
        return target


def _escape_filter_path(path: str) -> str:
    """Escape a filesystem path for embedding inside an ffmpeg filter graph."""
    for special, replacement in (
        ("\\", "\\\\"),
        (":", "\\:"),
        ("'", "\\'"),
        (",", "\\,"),
        ("[", "\\["),
        ("]", "\\]"),
    ):
        path = path.replace(special, replacement)
    return path
