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
pip install -e ".[whisper]"        # from a local checkout
pip install "motion-caption[whisper]"  # once published
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

## Gemini (optional transcription)

Cloud transcription behind the `ai` extra (same dependency as Gemini
annotation — no torch needed):

```bash
pip install -e ".[ai]"        # from a local checkout
pip install "motion-caption[ai]"  # once published
echo 'GEMINI_API_KEY=your-key' > .env   # .env is gitignored
set -a; source .env; set +a
```

```python
from motion_caption.video import GeminiTranscriptProvider

provider = GeminiTranscriptProvider(model="gemini-2.5-flash")
transcript = provider.transcribe("audio.wav")
```

- `GEMINI_API_KEY` env var supplies the key; `GEMINI_MODEL` sets the default
  model (constructor argument wins over the env var).
- The adapter uploads the file to Gemini, waits for it to become active, asks
  for JSON, and normalizes output (sorts, clamps overlaps, drops degenerate
  words) just like the WhisperX adapter. A missing install or failed
  transcription raises `TranscriptionError` with a hint.
- Audio longer than `chunk_seconds` (default 45s) is automatically split into
  overlapping clips that are transcribed separately and stitched back together,
  because Gemini's timestamps drift and fragment on multi-minute files. This
  keeps captions in sync all the way to the end of long videos. Tune with
  `chunk_seconds=`/`overlap_seconds=` on the constructor, or pass
  `chunk_seconds=None` to force a single call. Note: chunking multiplies API
  calls (a 4-minute video needs ~6), which can exhaust free-tier daily quotas
  faster.
- The prompt also asks Gemini to recommend a caption **theme** from the
  built-ins (`clean`, `music_video`, `cinematic`, `sport`, `news`) based on
  the lyrics' mood/genre/energy. The recommendation lands on
  `transcript.theme` (unknown names are dropped) and the pipeline honours it
  when you don't pass `--theme` — the compiler falls back to `clean`.
- For a full pipeline, pass the provider straight to `CaptionVideoPipeline` or
  `--transcript-provider gemini` on the CLI.

## Gemini (optional annotation)

```bash
pip install -e ".[ai]"        # from a local checkout
pip install "motion-caption[ai]"  # once published
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
pip install -e ".[video]"        # from a local checkout (opencv-python-headless)
pip install "motion-caption[video]"  # once published
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
| `GEMINI_API_KEY` | `motion_caption.ai`, `motion_caption.video.gemini` | Gemini annotation and transcription |
| `OPENAI_API_KEY` | `motion_caption.ai` | OpenAI annotation |
| `FFMPEG_PATH` / `FFPROBE_PATH` | `motion_caption.video.ffmpeg` | explicit binary paths |
| `WHISPER_MODEL` | `motion_caption.video.whisperx` | default WhisperX model |
| `GEMINI_MODEL` | `motion_caption.video.gemini` | default Gemini transcription model |

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
