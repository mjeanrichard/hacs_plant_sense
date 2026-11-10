"""Tests for helper functions."""

from __future__ import annotations

import pytest

from custom_components.plant_sense.helpers import (
    build_unique_id,
    is_newer_firmware,
    parse_firmware_version,
)


def test_build_unique_id() -> None:
    assert build_unique_id("aabbccddeeff") == "PlantSense-aabbccddeeff"


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.2", (1, 2)),
        ("v1.2", (1, 2)),
        ("1.2-dev", (1, 2)),
        (" 1.10 ", (1, 10)),
        ("2.0.1", (2, 0, 1)),
        ("abc", None),
        ("1.x", None),
        ("", None),
        ("-dev", None),
    ],
)
def test_parse_firmware_version(version: str, expected: tuple[int, ...] | None) -> None:
    assert parse_firmware_version(version) == expected


@pytest.mark.parametrize(
    ("candidate", "installed", "expected"),
    [
        ("1.1", "1.0", True),
        ("1.10", "1.9", True),  # numeric, not lexicographic
        ("2.0", "1.9", True),
        ("v1.1", "1.0", True),
        ("1.1.1", "1.1", True),
        ("1.1", "1.1", False),
        ("1.0", "1.1", False),
        ("1.1.0", "1.1", False),  # trailing zeros are equal
        ("1.1", "1.1-dev", False),  # device ignores the -dev suffix
        ("1.1", "1.2-dev", False),  # never "downgrade" a dev build
        ("garbage", "1.0", False),
        ("1.1", "garbage", False),
    ],
)
def test_is_newer_firmware(candidate: str, installed: str, *, expected: bool) -> None:
    assert is_newer_firmware(candidate, installed) is expected
