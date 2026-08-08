"""Deterministic snapshot comparison helpers.

Snapshots are committed files under ``tests/snapshots/``. Set
``MC_UPDATE_SNAPSHOTS=1`` to (re)write snapshots instead of comparing —
intended for intentional output changes only. Without the flag a missing or
mismatched snapshot fails with the path and a regeneration hint.

Text snapshots are compared byte-for-byte as UTF-8 (always terminated by a
newline); golden frames are compared as raw PNG bytes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

SNAPSHOT_ROOT = Path(__file__).resolve().parent / "snapshots"

_UPDATE_ENV = "MC_UPDATE_SNAPSHOTS"


def update_enabled() -> bool:
    """True when snapshots should be rewritten rather than compared."""
    return os.environ.get(_UPDATE_ENV) == "1"


def snapshot_path(*parts: str) -> Path:
    """Absolute path of a snapshot below ``tests/snapshots/``."""
    return SNAPSHOT_ROOT.joinpath(*parts)


def _compare(path: Path, data: bytes) -> None:
    if update_enabled() or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if update_enabled():
            return
        pytest.fail(
            f"snapshot missing: {path}\n"
            f"set {_UPDATE_ENV}=1 to generate it"
        )
    expected = path.read_bytes()
    if expected != data:
        pytest.fail(
            f"snapshot mismatch: {path}\n"
            f"set {_UPDATE_ENV}=1 to regenerate (only after an intentional change)"
        )


def assert_text_snapshot(value: str, *parts: str) -> None:
    """Compare ``value`` against ``tests/snapshots/<parts...>`` as UTF-8 bytes."""
    _compare(snapshot_path(*parts), value.encode("utf-8"))


def assert_bytes_snapshot(data: bytes, *parts: str) -> None:
    """Compare raw ``data`` against ``tests/snapshots/<parts...>``."""
    _compare(snapshot_path(*parts), data)
