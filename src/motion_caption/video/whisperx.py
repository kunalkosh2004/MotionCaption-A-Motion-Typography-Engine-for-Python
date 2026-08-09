"""Optional WhisperX adapter.

``whisperx`` is a heavy optional dependency (torch, etc.) and is **never**
imported by the core package. This adapter imports it lazily inside
``transcribe`` and reports a clear ``TranscriptionError`` when it is missing.

Output mapping (tolerant of API drift):

* word-level timestamps (``segment["words"]``) are preferred;
* if a model returns segments without word timestamps, each segment becomes
  one ``WordTimestamp`` (a usable fallback);
* results are pushed through ``normalize_transcript`` so out-of-order,
  overlapping or degenerate words never reach the compiler.

Errors: a missing install, a model that fails to load, or a transcription
failure all raise ``TranscriptionError`` with an actionable hint. An empty
result is *not* an error here — the pipeline's ``validate_transcript`` gate
reports it with the right message.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from motion_caption.errors import TranscriptionError
from motion_caption.models import Transcript, WordTimestamp
from motion_caption.video.transcript import normalize_transcript

# Models are cached per (name, device, compute_type) — loading is expensive
# and the adapter should not pay it per file.
_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}

_SUPPORTED_DEVICES = ("cpu", "cuda", "mps")


def _import_whisperx() -> Any:
    try:
        import whisperx  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise TranscriptionError(
            "WhisperX is not installed",
            hint="pip install 'motion-caption[whisper]' (or pip install whisperx)",
        ) from exc
    return whisperx


class WhisperXTranscriptProvider:
    """``TranscriptProvider`` backed by WhisperX word-level transcription.

    Args:
        model: model name (defaults to ``WHISPER_MODEL`` env or ``"base"``).
        device: ``"cpu"`` (default), ``"cuda"`` or ``"mps"``.
        language: ISO code (e.g. ``"en"``). ``None`` lets WhisperX detect it.
        compute_type: whisperx compute type (e.g. ``"float32"``, ``"int8"``).
    """

    name = "whisperx"

    def __init__(
        self,
        *,
        model: str | None = None,
        device: str = "cpu",
        language: str | None = None,
        compute_type: str = "float32",
    ) -> None:
        if device not in _SUPPORTED_DEVICES:
            raise ValueError(
                f"unsupported device {device!r}; expected one of {_SUPPORTED_DEVICES}"
            )
        self.model = model or os.environ.get("WHISPER_MODEL") or "base"
        self.device = device
        self.language = language
        self.compute_type = compute_type

    def transcribe(self, audio_path: str | Path) -> Transcript:
        """Transcribe an audio file into a word-timed ``Transcript``."""
        source = Path(audio_path)
        if not source.is_file():
            raise TranscriptionError(
                f"audio file does not exist: {source}",
                hint="extract the video audio first (FFmpegVideoProcessor.extract_audio)",
            )
        whisperx = _import_whisperx()
        cache_key = (self.model, self.device, self.compute_type)
        if cache_key not in _MODEL_CACHE:
            try:
                _MODEL_CACHE[cache_key] = whisperx.load_model(
                    self.model,
                    device=self.device,
                    compute_type=self.compute_type,
                    language=self.language,
                )
            except Exception as exc:
                raise TranscriptionError(
                    f"failed to load WhisperX model {self.model!r} on {self.device}: {exc}",
                    hint="check the model name is valid and the device is available",
                ) from exc
        try:
            audio = whisperx.load_audio(str(source))
            result = _MODEL_CACHE[cache_key].transcribe(audio)
        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError(
                f"WhisperX transcription failed: {exc}",
                hint="re-run on a valid audio file (16 kHz mono WAV)",
            ) from exc

        detected_language = str(result.get("language") or self.language or "en")
        words = self._extract_words(result)
        return normalize_transcript(
            Transcript(language=detected_language, words=words)
        )

    @staticmethod
    def _extract_words(result: dict[str, Any]) -> list[WordTimestamp]:
        """Flatten word timestamps; fall back to per-segment timestamps.

        Every segment contributes its words in order: word-level timestamps
        when present, otherwise the segment text re-split into evenly spaced
        words (so the caption engine still sees word granularity).
        """
        segments = result.get("segments") or []
        per_segment: list[list[WordTimestamp]] = []
        for segment in segments:
            items = segment.get("words") or []
            if items:
                segment_words: list[WordTimestamp] = []
                for item in items:
                    word_text = str(item.get("word") or item.get("text") or "").strip()
                    start, end = item.get("start"), item.get("end")
                    if not word_text or start is None or end is None:
                        continue  # missing timestamps on a word → skip it
                    segment_words.append(
                        WordTimestamp(
                            text=word_text,
                            start=float(start),
                            end=float(end),
                            confidence=float(item.get("score") or 1.0),
                        )
                    )
                per_segment.append(segment_words)
            else:
                segment_text = str(segment.get("text") or "").strip()
                start, end = segment.get("start"), segment.get("end")
                if segment_text and start is not None and end is not None:
                    per_segment.append(
                        _split_segment_words(
                            [
                                WordTimestamp(
                                    text=segment_text,
                                    start=float(start),
                                    end=float(end),
                                )
                            ]
                        )
                    )
        return [word for group in per_segment for word in group]


def _split_segment_words(segments: list[WordTimestamp]) -> list[WordTimestamp]:
    """Turn per-segment timestamps into evenly split per-word timestamps."""
    result: list[WordTimestamp] = []
    for segment in segments:
        tokens = segment.text.split()
        if not tokens:
            continue
        span = segment.end - segment.start
        step = span / len(tokens)
        for index, token in enumerate(tokens):
            start = segment.start + step * index
            result.append(
                WordTimestamp(
                    text=token,
                    start=round(start, 6),
                    end=round(start + step, 6),
                    confidence=segment.confidence,
                )
            )
    return result
