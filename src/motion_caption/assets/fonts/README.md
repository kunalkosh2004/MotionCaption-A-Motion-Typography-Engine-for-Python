# Bundled fonts

`NotoSans-Regular.ttf`, `NotoSans-Bold.ttf` and `NotoSans-Italic.ttf` are
bundled so captions render readable text on **any** runtime — including
minimal Linux/Docker images that have no system fonts. They are the
guaranteed, Unicode-capable fallback in every theme stack.

- **Family:** Noto Sans (Regular 400 / Bold 700 / Italic 400)
- **Source:** Google Noto fonts, packaged by Debian `fonts-noto-core`
  (`/usr/share/fonts/truetype/noto/`), pulled from the container image.
- **Coverage:** Latin + Latin Extended (accented text like `é`), digits,
  punctuation, apostrophes (`'` `’`), typographic symbols (em/en dashes
  `—` `–`), Greek, Cyrillic, and more.
- **License:** SIL Open Font License 1.1 — see `OFL.txt`. Bundling and
  redistribution with software are explicitly permitted.

## Why a bundled font

The compiler resolves theme font stacks against the system font catalog.
On a developer's macOS the stacks (Helvetica, Arial, Georgia, …) resolve
fine; on a slim Linux container (`python:3.12-slim` + `fonts-noto-core`)
those families do not exist, and only the Indic fallbacks
(`Noto Sans Devanagari`/`Gurmukhi`) resolved — so English captions were
drawn with a Devanagari font and rendered as `□` boxes.

The bundled Noto Sans guarantees a Latin-capable face is always available,
and the theme stacks now request it explicitly (`Noto Sans` after
`DejaVu Sans` in `themes/catalog.py`), so it is selected *before* the
Indic fallbacks in the container. System fonts still win when present.
