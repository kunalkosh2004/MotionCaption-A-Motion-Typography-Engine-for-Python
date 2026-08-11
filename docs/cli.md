# Command Line

`motion-caption` is the thin application shell over the library. Install it
with `pip install -e .` (the console script is declared in `pyproject.toml`).

```bash
motion-caption --help
motion-caption --version
```

All failures print `error: <what> (<how to fix>)` to stderr and exit 1.

## caption — the whole pipeline

```bash
motion-caption caption input.mp4 \
    --theme music_video \
    --preset youtube_shorts \
    --ai gemini \
    -o output.mp4
```

| Flag | Meaning |
|---|---|
| `--theme` | theme name (default `clean`); omit for auto — the transcript may recommend one (e.g. Gemini picks it from the lyrics' vibe) |
| `--preset` (alias `--platform`) | `youtube_shorts`, `tiktok`, `instagram_reels`, `youtube_landscape`, `square` |
| `--ai PROVIDER` | annotate first with `gemini` or `openai` (needs an API key); omit for rule-based |
| `--transcript-provider PROVIDER` | transcribe the audio with `gemini` (needs `GEMINI_API_KEY`) or `whisperx` (needs the `whisper` extra); omit to use a `--transcript` file or rule-based placeholders |
| `--transcript FILE` | skip transcription; read a `Transcript` JSON file |
| `--fps N` | frame rate (default 30) |
| `--resolution WxH` | output resolution (default: input video size) |
| `-o FILE` | output (default `<input>_captioned.mp4`) |

Deterministic, offline mode (no AI, no ASR — just a transcript file):

```bash
motion-caption caption input.mp4 --transcript transcript.json -o output.mp4
```

## compile — request → timeline

```bash
motion-caption compile request.json -o timeline.json
```

`request.json` is a serialized `CaptionRequest` — see `docs/compiler.md` or
`docs/integrations.md` for the shape. `compile` validates the JSON and
reports the first schema problem with a hint.

## render — timeline → PNG frames

```bash
motion-caption render timeline.json --resolution 1080x1920 --fps 30 -o frames/
```

Writes `000000.png, 000001.png, …` (the pattern `FFmpegVideoProcessor`
expects). `--resolution` overrides the timeline's native resolution.

## export — timeline → backend

```bash
motion-caption export timeline.json --format ass -o captions.ass
motion-caption export timeline.json --format json -o timeline.json
```

## Listings

```bash
motion-caption themes        # built-in theme names
motion-caption animations    # animation templates
motion-caption exporters     # exporter backends (ass, json)
```

## info — inspect a media file

```bash
motion-caption info input.mp4
```

Prints JSON metadata from `ffprobe` (resolution, fps, duration, codecs,
audio presence). Requires FFmpeg on `PATH` (or `FFMPEG_PATH`).
