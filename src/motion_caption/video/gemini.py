"""Optional Gemini transcript provider (cloud ASR behind the ``ai`` extra).

``google-genai`` is an optional dependency and is **never** imported by the
core package. This adapter imports it lazily inside ``transcribe`` and reports
a clear ``TranscriptionError`` when it is missing.

Gemini is a *text* transcription engine: it does not return reliable
word-level timestamps, so this provider requests segment boundaries (start/end
in seconds) and splits each segment's words evenly across its span. Caption
block timing (fade/slide/pop) stays accurate; per-word effects (karaoke) are
approximate by design. Audio longer than ``chunk_seconds`` is split into
overlapping clips and each is transcribed separately — Gemini timestamps drift
and fragment on multi-minute files, and short clips keep the per-segment
timing trustworthy (this is what keeps captions in sync to the very end).

Errors: a missing install, a missing API key, a model that fails, or a
transcription failure all raise ``TranscriptionError`` with an actionable
hint. An empty result is *not* an error here — the pipeline's
``validate_transcript`` gate reports it with the right message.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from motion_caption.errors import FFmpegError, InvalidVideoError, TranscriptionError
from motion_caption.models import Transcript, WordTimestamp
from motion_caption.video.ffmpeg import FFmpegVideoProcessor, temporary_directory
from motion_caption.video.transcript import normalize_transcript, split_segment_words

# The model returns JSON: segments with numeric start/end (seconds), the
# verbatim spoken text, and a recommended caption theme. Word timing is
# derived client-side by splitting each segment evenly — Gemini's own word
# timestamps are not trustworthy.
_PROMPT = """Transcribe the attached audio file.
Return ONLY a JSON object with exactly this schema:
{
  "language": "<ISO 639-1 language code, e.g. \\"en\\">",
  "theme": "<best matching caption theme name>",
  "segments": [
    {"start": <float seconds>, "end": <float seconds>, "text": "<verbatim spoken text>"}
  ]
}
Rules:
- Give the start and end of every segment in seconds from the start of the audio.
- Include every spoken word; do not paraphrase, summarize or drop words.
- One segment per utterance or pause group.
- "start" and "end" must be numbers (seconds), never clock strings.
- "theme" must be the single best-fitting caption theme for this song's mood,
  genre and energy, chosen ONLY from: "clean", "music_video", "cinematic",
  "sport", "news"."""

_THEME_NAMES = frozenset({"clean", "music_video", "cinematic", "sport", "news"})

_FILE_STATE_ACTIVE = "ACTIVE"
_FILE_STATE_FAILED = frozenset({"FAILED", "FAILED_SAFE"})


def _import_genai() -> Any:
    try:
        from google import genai  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise TranscriptionError(
            "google-genai is not installed",
            hint="pip install 'motion-caption[ai]' (or pip install google-genai)",
        ) from exc
    return genai


def _state_name(state: Any) -> str:
    if state is None:
        return ""
    return getattr(state, "name", None) or str(state)


def _wait_until_active(client: Any, uploaded: Any, timeout: float) -> Any:
    deadline = time.monotonic() + timeout
    audio_file = uploaded
    while _state_name(audio_file.state) != _FILE_STATE_ACTIVE:
        state = _state_name(audio_file.state)
        if state in _FILE_STATE_FAILED:
            raise TranscriptionError(
                f"Gemini rejected the audio file (state={state})",
                hint="re-export the audio as 16 kHz mono WAV and retry",
            )
        if time.monotonic() >= deadline:
            raise TranscriptionError(
                "timed out waiting for Gemini to process the audio file",
                hint="retry, or split the audio into shorter clips",
            )
        time.sleep(0.5)
        audio_file = client.files.get(name=uploaded.name)
    return audio_file


def _call_gemini(
    genai: Any,
    api_key: str,
    model: str,
    audio_path: Path,
    timeout: float,
) -> str:
    """Upload ``audio_path`` and return the model's raw text response."""
    client = genai.Client(api_key=api_key)
    try:
        uploaded = client.files.upload(file=str(audio_path))
    except Exception as exc:
        raise TranscriptionError(
            f"Gemini audio upload failed: {exc}",
            hint="check the API key and network; the file must be readable audio",
        ) from exc
    audio_file = _wait_until_active(client, uploaded, timeout)
    response = client.models.generate_content(
        model=model,
        contents=[audio_file, _PROMPT],
        config=genai.types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return response.text or ""


def _as_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0.0 else default


def _words_from_items(items: list[Any]) -> list[WordTimestamp]:
    words: list[WordTimestamp] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("word") or "").strip()
        if not text:
            continue
        start = _as_float(item.get("start"), -1.0)
        end = _as_float(item.get("end"), -1.0)
        if start < 0.0 or end <= start:
            continue
        confidence = _as_float(item.get("confidence") or item.get("score"), 1.0)
        words.append(
            WordTimestamp(
                text=text,
                start=start,
                end=end,
                confidence=max(0.0, min(1.0, confidence)),
            )
        )
    return words


def _words_from_segments(segments: list[Any]) -> list[WordTimestamp]:
    words: list[WordTimestamp] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        start = _as_float(segment.get("start"), -1.0)
        end = _as_float(segment.get("end"), -1.0)
        if start < 0.0 or end <= start:
            continue
        inner = segment.get("words")
        if isinstance(inner, list) and inner:
            words.extend(_words_from_items(inner))
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        words.extend(
            split_segment_words([WordTimestamp(text=text, start=start, end=end)])
        )
    return words


def _coerce_theme(value: Any) -> str | None:
    """Accept a theme name only when it is a known built-in theme."""
    if not isinstance(value, str):
        return None
    name = value.strip().lower()
    return name if name in _THEME_NAMES else None


def _parse_transcript(content: str) -> Transcript:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    if not text:
        return Transcript(language="en", words=[])
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini returned invalid JSON: {content[:80]!r}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Gemini returned unexpected JSON: {content[:80]!r}")

    language = payload.get("language") or "en"
    theme = _coerce_theme(payload.get("theme"))
    segments = payload.get("segments")
    if isinstance(segments, list) and segments:
        words = _words_from_segments(segments)
        return normalize_transcript(
            Transcript(language=language, words=words, theme=theme)
        )
    words = payload.get("words")
    if isinstance(words, list) and words:
        return normalize_transcript(
            Transcript(language=language, words=_words_from_items(words), theme=theme)
        )
    return Transcript(language=language, words=[], theme=theme)


def _merge_chunk_transcripts(
    transcripts: list[Transcript],
    *,
    chunk_seconds: float,
    overlap_seconds: float,
) -> Transcript:
    """Stitch per-chunk transcripts back into one continuous transcript.

    Chunk ``i`` covers ``[i*step, i*step+chunk_seconds)`` where ``step =
    chunk_seconds - overlap_seconds``, so its first ``overlap_seconds`` of
    words re-transcribe the tail of chunk ``i-1``. Discarding that head (and
    offsetting the rest) yields gapless, duplicate-free speech order.
    """
    if not transcripts:
        return Transcript(language="en", words=[])
    step = chunk_seconds - overlap_seconds
    words: list[WordTimestamp] = []
    for index, transcript in enumerate(transcripts):
        offset = index * step
        for word in transcript.words:
            # The chunk's first overlap_seconds (local time) re-transcribe the
            # tail of the previous chunk; drop them so speech stays continuous.
            if index > 0 and word.start < overlap_seconds:
                continue
            words.append(
                WordTimestamp(
                    text=word.text,
                    start=word.start + offset,
                    end=word.end + offset,
                    confidence=word.confidence,
                )
            )
    theme = next((transcript.theme for transcript in transcripts if transcript.theme), None)
    language = next(
        (transcript.language for transcript in transcripts if transcript.language), "en"
    )
    return normalize_transcript(Transcript(language=language, words=words, theme=theme))


class GeminiTranscriptProvider:
    """``TranscriptProvider`` backed by Gemini cloud transcription.

    Args:
        api_key: Gemini API key; falls back to ``GEMINI_API_KEY``.
        model: model id (default ``"gemini-2.5-flash"``).
        timeout: seconds to wait for the uploaded audio to become ready.
        chunk_seconds: audio longer than this is split into overlapping
            clips and transcribed in pieces (default 45s). Set to ``None``
            or ``0`` to transcribe the whole file in one call.
        overlap_seconds: overlap between adjacent clips; the duplicate
            tail is discarded on merge.
        ffmpeg: ``FFmpegVideoProcessor`` used to probe and split long audio
            (a default is created when omitted).
    """

    name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "gemini-2.5-flash",
        timeout: float = 120.0,
        chunk_seconds: float = 45.0,
        overlap_seconds: float = 3.0,
        ffmpeg: FFmpegVideoProcessor | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.chunk_seconds = chunk_seconds
        self.overlap_seconds = overlap_seconds
        self.ffmpeg = ffmpeg or FFmpegVideoProcessor(timeout=timeout)

    def _audio_duration(self, source: Path) -> float | None:
        try:
            duration = self.ffmpeg.duration(source)
        except (FFmpegError, InvalidVideoError):
            return None
        return duration

    def _transcribe_chunked(
        self,
        genai: Any,
        api_key: str,
        source: Path,
    ) -> Transcript:
        with temporary_directory("motioncaption-chunks-") as scratch:
            chunks = self.ffmpeg.split_audio(
                source,
                scratch,
                chunk_seconds=self.chunk_seconds,
                overlap_seconds=self.overlap_seconds,
            )
            transcripts = [
                _parse_transcript(
                    _call_gemini(genai, api_key, self.model, chunk, self.timeout)
                )
                for chunk in chunks
            ]
        return _merge_chunk_transcripts(
            transcripts,
            chunk_seconds=self.chunk_seconds,
            overlap_seconds=self.overlap_seconds,
        )

    def transcribe(self, audio_path: str | Path) -> Transcript:
        """Transcribe an audio file into a word-timed ``Transcript``."""
        source = Path(audio_path)
        if not source.is_file():
            raise TranscriptionError(
                f"audio file does not exist: {source}",
                hint="extract the video audio first (FFmpegVideoProcessor.extract_audio)",
            )
        api_key = self.api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise TranscriptionError(
                "GeminiTranscriptProvider: no api_key",
                hint="pass api_key=... or export GEMINI_API_KEY",
            )
        genai = _import_genai()
        try:
            if self.chunk_seconds and self.chunk_seconds > 0:
                duration = self._audio_duration(source)
                if duration is not None and duration > self.chunk_seconds:
                    return self._transcribe_chunked(genai, api_key, source)
            content = _call_gemini(genai, api_key, self.model, source, self.timeout)
            return _parse_transcript(content)
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError(
                f"Gemini transcription failed: {exc}",
                hint="check the API key and network; re-run on a valid audio file",
            ) from exc
