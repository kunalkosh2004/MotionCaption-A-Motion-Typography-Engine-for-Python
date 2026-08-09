"""Platform preset tests."""

from __future__ import annotations

import pytest

from motion_caption.video.presets import (
    PLATFORM_PRESETS,
    PlatformPreset,
    available_presets,
    platform_preset,
)


def test_builtin_presets_have_sane_shapes() -> None:
    assert PlatformPreset.youtube_shorts().resolution == (1080, 1920)
    assert PlatformPreset.tiktok().resolution == (1080, 1920)
    assert PlatformPreset.instagram_reels().resolution == (1080, 1920)
    assert PlatformPreset.youtube_landscape().resolution == (1920, 1080)
    assert PlatformPreset.square().resolution == (1080, 1080)


def test_presets_carry_safe_areas_and_fps() -> None:
    preset = PlatformPreset.youtube_shorts()
    assert preset.fps == 30
    assert preset.safe_area.bottom > 0.0
    assert preset.name == "youtube_shorts"


def test_request_fields_are_json_friendly() -> None:
    fields = PlatformPreset.youtube_shorts().request_fields()
    assert fields["resolution"] == "1080x1920"
    assert fields["platform"] == "youtube_shorts"
    assert "safe_area" in fields


def test_lookup_by_name_and_alias() -> None:
    assert platform_preset("youtube_shorts").name == "youtube_shorts"
    assert platform_preset("shorts").name == "youtube_shorts"
    assert platform_preset("reels").name == "instagram_reels"


def test_unknown_preset_raises_key_error() -> None:
    with pytest.raises(KeyError, match="unknown platform preset"):
        platform_preset("vhs")


def test_registry_and_listing() -> None:
    assert set(available_presets()) == {
        "youtube_shorts",
        "tiktok",
        "instagram_reels",
        "youtube_landscape",
        "square",
    }
    assert set(PLATFORM_PRESETS) == set(available_presets())
