# Integrations

Everything external lives *above* the compiler. The core package imports
none of these — each integration is behind an optional extra and lazy
imports, so `pip install motion-caption` stays tiny and the compiler stays
deterministic.

## FFmpeg (required for the video pipeline)

Used for probing, audio extraction, frame encoding, audio muxing and ASS
burning. Nothing loads it at import time.

```bash
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Debian/Ubuntu
```

- Binary resolution: `FFMPEG_PATH` / `FFPROBE_PATH` env vars, then `PATH`.
- `motion-caption info video.mp4` is the fastest way to verify it works.
- Errors are typed (`FFmpegError`, `InvalidVideoError`) with actionable hints.

## WhisperX (optional ASR)

Word-level transcription behind the `whisper` extra:

```bash
pip install -e "motion-caption[whisper]"
```

```python
from motion_caption.video import WhisperXTranscriptProvider

provider = WhisperXTranscriptProvider(model="large-v2", device="cpu", language="en")
transcript = provider.transcribe("audio.wav")
```

- `WHISPER_MODEL` env var sets the default model.
- The adapter normalizes output (sorts, clamps overlaps, drops degenerate
  words) and falls back to per-segment timestamps when a model returns no
  word-level words. A missing install or failed transcription raises
  `TranscriptionError` with a hint.
- `whisperx` pulls in torch — hence the optional extra.

## Gemini (optional annotation)

```bash
pip install -e "motion-caption[ai]"
echo 'GEMINI_API_KEY=your-key' > .env   # .env is gitignored
set -a; source .env; set +a
```

```python
from motion_caption.ai import AI_REGISTRY, annotate

annotated = annotate(request, AI_REGISTRY.get("gemini"))
timeline = compile(annotated)
```

- Default model `gemini-2.5-flash` (some keys carry no quota on older
  models); override with `GeminiProvider(model=...)`.
- SDK is `google-genai` (the legacy `google-generativeai` is EOL).
- Missing key → `AIProviderError` with an install/key hint. Annotation is
  entirely optional: no provider, no key → rule-based pipeline.

## OpenAI (optional annotation)

```bash
echo 'OPENAI_API_KEY=your-key' >> .env
set -a; source .env; set +a
```

```python
from motion_caption.ai import AI_REGISTRY, annotate

annotated = annotate(request, AI_REGISTRY.get("openai"))
```

Default model `gpt-4o-mini`; override with `OpenAIProvider(model=...)`.

## Face detection (optional)

```bash
pip install -e "motion-caption[video]"     # opencv-python-headless
```

```python
from motion_caption.video import OpenCVFaceDetector

pipeline = CaptionVideoPipeline(theme="clean", face_detector=OpenCVFaceDetector())
```

Detection runs on sampled frames; the union of face boxes becomes the
avoidance zone. Any object with `detect(frame) -> list[Box]` works.

## Environment variables

| Variable | Used by | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `motion_caption.ai` | Gemini annotation |
| `OPENAI_API_KEY` | `motion_caption.ai` | OpenAI annotation |
| `FFMPEG_PATH` / `FFPROBE_PATH` | `motion_caption.video.ffmpeg` | explicit binary paths |
| `WHISPER_MODEL` | `motion_caption.video.whisperx` | default WhisperX model |

Keys never appear in logs; the compiler never loads `.env`.

## JSON request format

`motion-caption compile request.json` consumes a serialized
`CaptionRequest`. The minimal shape:

```json
{
  "transcript": {
    "words": [
      {"text": "Hello", "start": 0.0, "end": 0.5},
      {"text": "world", "start": 0.5, "end": 1.0}
    ]
  },
  "theme": "music_video",
  "platform": "youtube_shorts"
}
```

Load it programmatically with `motion_caption.io.load_request(path)`, then
`compile(request)`. The timeline round-trips through JSON the same way
(`load_timeline` / `save_timeline`).
