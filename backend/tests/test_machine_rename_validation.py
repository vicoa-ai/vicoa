"""Pure unit tests for machine display-name validation (no DB).

Covers plans/machine-management.md D15 — rename validation lives in a small
deep module so the trim/empty/too-long rules are testable without a database.
"""

from __future__ import annotations

import pytest

from backend.api.machines import _validated_display_name


def test_trims_surrounding_whitespace() -> None:
    assert _validated_display_name("  my-laptop  ") == "my-laptop"


def test_valid_name_passes_through() -> None:
    assert _validated_display_name("Work MacBook") == "Work MacBook"


@pytest.mark.parametrize("raw", ["", "   ", "\t\n", None])
def test_empty_or_whitespace_raises(raw: str | None) -> None:
    with pytest.raises(ValueError):
        _validated_display_name(raw)


def test_over_255_raises() -> None:
    with pytest.raises(ValueError):
        _validated_display_name("x" * 256)


def test_exactly_255_is_allowed() -> None:
    name = "x" * 255
    assert _validated_display_name(name) == name
