"""Shapes of the pinned agent CLI builds in ``vicoa.agent_releases``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

ArchiveKind = Literal["raw", "tar.gz", "zip"]


@dataclass(frozen=True)
class ReleaseAsset:
    """One platform's build of an agent CLI."""

    url: str
    sha256: str
    size: int
    #: "raw" is the executable itself; the others unpack into a directory.
    archive: ArchiveKind
    #: Where the CLI sits once unpacked, relative to the install directory.
    binary: str
    #: Same bytes from a second host, tried when the first fails.
    fallback_url: str | None = None


@dataclass(frozen=True)
class PinnedRelease:
    """The version of an agent CLI this daemon release installs."""

    agent: str
    version: str
    #: Keyed by the vendor's own platform name (see ``agent_install.asset_key``).
    assets: Mapping[str, ReleaseAsset]
