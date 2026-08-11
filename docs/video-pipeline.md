# Video Pipeline

The application layer turns a raw video file into a captioned video:

```text
video.mp4
   │  FFmpegVideoProcessor.probe()      — validate + inspect
   ▼
metadata (resolution, fps, duration, audio)
   │
   ├─ extract_audio() → 16 kHz mono WAV
   │        │
   │        ▼  TranscriptProvider.transcribe()
   │     Transcript  (or load one from JSON — no transcription needed)
   │
   ├─ [FaceDetector] → sampled face boxes (union avoidance zones)
   │
   ├─ [AIProvider]   → annotate() → llm_annotations (optional; needs a key)
   │
   ▼
CaptionRequest → Compiler → SubtitleTimeline
   │
   ▼  TimelineRenderer.render_sequence_to_directory()  (streamed PNGs)
frames/ 000000.png …  →  FFmpegVideoProcessor.render_frames_to_video()
   │
   ▼  mux_audio() (original audio, full quality, stream copy)
final.mp4
```

## One call

```python
from motion_caption.video import CaptionVideoPipeline

pipeline = CaptionVideoPipeline(
    theme="music_video",
    preset="youtube_shorts",          # 1080x1920 + safe area + 30 fps
    transcript_provider=WhisperXTranscriptProvider(),  # optional (or GeminiTranscriptProvider / FakeTranscriptProvider)
    ai_provider="gemini",             # optional; needs GEMINI_API_KEY
)
result = pipeline.process("input.mp4", "output.mp4")

print(result.output_video)        # Path
print(result.event_count, result.word_count, result.frames_rendered)
print(result.timeline)            # the compiled SubtitleTimeline
```

Without a transcript provider or AI, pass a `Transcript` (e.g. from a JSON
file) and everything stays deterministic and offline:

```python
from motion_caption.io import load_transcript

result = pipeline.process("input.mp4", "output.mp4",
                          transcript=load_transcript("transcript.json"))
```

Theme resolution order: explicit `theme=` (or `--theme`) wins, then
`transcript.theme` (a provider recommendation, e.g. Gemini's), then `clean`.

## Pieces

| Component | Module | Responsibility |
|---|---|---|
| `FFmpegVideoProcessor` | `motion_caption.video.ffmpeg` | probe / extract audio / extract frame / encode PNGs / mux / burn ASS; arg-array `subprocess`, timeouts, `FFMPEG_PATH` env |
| `TranscriptProvider` (protocol) | `motion_caption.video.transcript` | any object with `transcribe(audio_path) -> Transcript` |
| `FakeTranscriptProvider` | `motion_caption.video.transcript` | deterministic word timings for tests/demos || `WhisperXTranscriptProvider` | `motion_caption.video.whisperx` | word-level ASR behind the `whisper` extra (lazy import) |
| `GeminiTranscriptProvider` | `motion_caption.video.gemini` | cloud transcription behind the `ai` extra (lazy import); `GEMINI_API_KEY` / `GEMINI_MODEL` |
| `FaceDetector` (protocol) / `OpenCVFaceDetector` | `motion_caption.video.faces` | per-frame boxes; `detect_faces_for_video()` samples frames and unions boxes |
| `PlatformPreset` | `motion_caption.video.presets` | shorts / tiktok / reels / landscape / square bundles |
| `CaptionVideoPipeline` | `motion_caption.video.pipeline` | orchestration; returns `PipelineResult` |

## Streaming, not memory

`TimelineRenderer.render_sequence_to_directory` writes one PNG at a time —
an hour-long 4K video never materializes as an image list. Intermediate
frames, extracted audio and the silent intermediate live in a temporary
workspace that is removed when `process()` returns; only the output video
survives.

## Face-aware placement

`CaptionRequest.faces` already drives face-aware avoidance in the compiler.
The pipeline fills it from a detector:

```python
pipeline = CaptionVideoPipeline(
    theme="clean",
    face_detector=OpenCVFaceDetector(),   # needs `motion-caption[video]`
    ...
)
```

Faces are detected on a handful of sampled frames (default 8) and the union
of boxes becomes the avoidance zone — conservative by design, cheap by
construction. Swap in any `FaceDetector` (YOLO, MediaPipe, …) without
touching the compiler.

## Determinism guarantee

The compiler is unchanged by this layer: same `CaptionRequest` → same
`SubtitleTimeline` bytes. AI output is precomputed *input* (`llm_annotations`);
FFmpeg only muxes and encodes. No random seeds, no wall-clock dependence.
