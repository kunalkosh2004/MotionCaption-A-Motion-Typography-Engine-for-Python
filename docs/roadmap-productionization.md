# Productionization Roadmap — Audit & Plan

Status: **All milestones complete** · **501 tests passing, ruff clean**

This document records the audit performed before the productionization effort and
the milestone-by-milestone plan. Each milestone lands as its own commit after
`pytest` is green.

---

## 1. Audit — what already exists (verified against code, not docs)

The compiler architecture described in `GUIDE.md` / `docs/compiler.md` is real and
working:

| Layer | Status | Notes |
|---|---|---|
| `models` (Transcript, Segment, Word, WordTimestamp, keyframes, units, colors) | ✅ implemented | pydantic, deterministic |
| `segmentation` (pauses/sentence/strict) | ✅ implemented | registry: `SEGMENTATION_REGISTRY` |
| `emphasis` (rule-based scoring) | ✅ implemented | registry: `EMPHASIS_REGISTRY` → `rules` |
| `reading` (pacing) | ✅ implemented | |
| `themes` (spec + catalog + resolve) | ✅ implemented | 6 built-ins incl. `default`; `THEME_REGISTRY` |
| `typography` (style, measure, fonts) | ✅ implemented | system catalog + path-bound fonts, lazy fontTools |
| `layout` / `placement` | ✅ implemented | face-aware placement exists in core |
| `animations` / `easing` | ✅ implemented | 15 animation templates, 7 easing families |
| `compiler` (normalize→assemble) | ✅ implemented | `Compiler`, `compile`, `default_compiler`; caches (CompiledThemeCache, TimelineCache) |
| `ir` (SubtitleTimeline + tracks) | ✅ implemented | canonical IR consumed by every backend |
| `render` (TimelineRenderer) | ✅ implemented | Pillow frames; `render_frame` / `render_sequence` |
| `exporters` (ass, json) | ✅ implemented | `EXPORTER_REGISTRY`; `build_ass` facade |
| `ai` (gemini, openai) | ✅ implemented | `AIProvider` protocol, `annotate()`, lazy SDK imports, `AI_REGISTRY` |
| `plugins` (load_plugins, PLUGIN_GROUPS) | ✅ implemented | |
| tests | ✅ 389 passing | incl. golden frames, snapshots (now checkout-portable), benchmarks |

## 2. Audit — findings

1. **Snapshot portability bug (fixed in this milestone).** The committed timeline
   snapshot embedded the absolute repo path (`/Users/.../MotionCaption...`), so it
   could only pass on the machine that generated it. Now the repo root is
   normalized to a `<REPO_ROOT>` placeholder before comparison — byte-stable on
   any checkout. (`tests/test_snapshots.py`, `tests/snapshots/timeline/golden.json`)
2. **Unused core dependency.** `opencv-python-headless>=4.8` is declared in
   `[project.dependencies]` but **nothing imports `cv2`**. It belongs behind an
   optional extra (moved in the video/faces milestone) so the deterministic
   compiler install stays light.
3. **No application layer.** No `motion_caption/video/`, no FFmpeg bridge, no
   transcript providers, no CLI, no `errors.py`, no `examples/`/`scripts/`.
   The library is complete; the *product* is not.
4. **No placeholders or stubs.** Zero `TODO`/`FIXME`/`NotImplementedError` in
   `src/`; the three `pass` statements in `typography/fonts.py` are defensive
   exception swallows.
5. **Repo hygiene (fixed).** `.DS_Store` was tracked; now untracked and ignored.
6. `.env` is already gitignored (holds `GEMINI_API_KEY`); `ai` extra installs
   `google-genai` (modern SDK) + `openai`; a `whisper` extra (`whisperx>=0.3`)
   already exists.

## 3. Milestone plan

| # | Milestone | Deliverable | Commit style |
|---|---|---|---|
| 0 | Audit + baseline repair | this doc; snapshot portability; repo hygiene | ✅ done |
| 1 | Error layer | `motion_caption/errors.py`: `MotionCaptionError` hierarchy (+ `RequestIOError`) with actionable messages | ✅ done |
| 2 | FFmpeg layer | `motion_caption/video/ffmpeg.py`: `FFmpegVideoProcessor` (probe, extract_audio, extract_frame, frames→video, mux, burn), arg-array subprocess, timeouts, temp-dir management, `FFMPEG_PATH` env | ✅ done |
| 3 | Transcript providers | `motion_caption/video/transcript.py`: `TranscriptProvider` protocol, validation (empty/malformed/overlap), deterministic `FakeTranscriptProvider` | ✅ done |
| 4 | WhisperX adapter | optional adapter behind the `whisper` extra; word-level output → `Transcript`; graceful missing-install errors | ✅ done |
| 5 | Video pipeline | `CaptionVideoPipeline.process()` orchestration (probe → audio → transcript → AI annotate → compile → **streamed** frame render → encode → mux → result); no full-sequence RAM hold | ✅ done |
| 6 | Face detection | `FaceDetector` protocol + `OpenCVFaceDetector` + sampled union detection; no compiler changes | ✅ done |
| 7 | Platform presets | `motion_caption/video/presets.py`: shorts/tiktok/reels/landscape/square → resolution + safe area + fps | ✅ done |
| 8 | JSON request IO | `motion_caption/io.py`: load/save request, transcript, timeline; typed errors | ✅ done |
| 9 | CLI | `motion-caption` entry point: `caption`, `compile`, `render`, `export`, `themes`, `animations`, `exporters`, `info` | ✅ done |
| 10 | Extras + docs | OpenCV moved to the `video` extra; `all` extra; `docs/video-pipeline.md`, `docs/cli.md`, `docs/integrations.md`; README updated | ✅ done |
| 11 | Final sweep | full suite, ruff, reviewer pass, acceptance checklist, real-FFmpeg e2e proof | ✅ done |

## 4. Acceptance checklist (verified, not claimed)

| Task requirement | Result |
|---|---|
| `pipeline.process("input.mp4", "output.mp4")` | ✅ `CaptionVideoPipeline` — unit + integration tested |
| `motion-caption caption input.mp4 --theme music_video --preset youtube_shorts --ai gemini -o out.mp4` | ✅ CLI wired; real-FFmpeg e2e proved the offline variant |
| Deterministic mode `--no-ai --transcript t.json` | ✅ `--transcript` verified live (typed error paths too) |
| Library mode (compile → render_frame/render_sequence → ASS/JSON) | ✅ unchanged public API, still green |
| Architecture (AI/WhisperX/FFmpeg/YOLO outside compiler) | ✅ application layer only; compiler untouched |
| Compiler deterministic; no LLM/FFmpeg inside stages | ✅ reviewer-verified; golden snapshots still pass |
| Error handling (typed + hints) | ✅ MotionCaptionError hierarchy incl. `MissingDependencyError`, `RequestIOError` |
| Tests: mocks for AI/FFmpeg; no external API in suite | ✅ all provider/SDK calls mocked |
| Real end-to-end (small fixture, no external AI) | ✅ 3 s testsrc+sine → 91 frames → h264+aac MP4, captions verified on pixels |
| Docs reflect reality | ✅ README/GUIDE/docs updated; only shipped features documented |

## 5. Hard constraints carried through every milestone

- `SubtitleTimeline` remains the canonical IR; backends never measure/layout/place/
  animate/LLM-call on their own.
- No AI / WhisperX / FFmpeg / YOLO dependency inside the compiler.
- Determinism: same `CaptionRequest` → same `SubtitleTimeline`; reuse the existing
  caches; no wall-clock/randomness in the core.
- Everything new is additive; existing public API stays backward compatible.
- AI stays optional: no API key → rule-based segmentation/emphasis still works.
- Tests: mocks for AI/FFmpeg; one deterministic end-to-end (fake transcript,
  tiny fixture, no external APIs).
