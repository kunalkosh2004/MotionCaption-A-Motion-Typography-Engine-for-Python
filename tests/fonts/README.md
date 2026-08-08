# Pinned test fonts

`Roboto-Regular.ttf` is bundled so golden-frame and snapshot tests render
identically on every machine and in CI — no dependence on system fonts.

- **Family:** Roboto
- **Weight:** Regular (400)
- **Source:** [fontsource](https://fontsource.org/fonts/roboto), the
  `latin-400-normal` subset, fetched from the jsDelivr CDN:
  `https://cdn.jsdelivr.net/fontsource/fonts/roboto@latest/latin-400-normal.ttf`
- **License:** Roboto is licensed under the
  [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

The snapshot/golden tests reference this file by **path** (via
`tests/pinned.py`), so resolution never touches the system font catalog.

**Version sensitivity:** the committed golden PNG is byte-stable only for the
Pillow/FreeType versions that generated it. If a fresh environment (e.g. a
newer Pillow in CI) reports a golden-frame mismatch, regenerate the PNG there
— a pixel-identical result across Pillow versions is not guaranteed.

Regenerate the snapshots after intentionally changing rendering output with:

```sh
MC_UPDATE_SNAPSHOTS=1 .venv/bin/python -m pytest tests/test_snapshots.py tests/test_golden.py -q
```
