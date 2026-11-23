#!/usr/bin/env python3
"""Regenerate ``src/vicoa/agent_releases.py``: the agent CLI builds a daemon
release may download, pinned to exact versions with their SHA-256 and size.

Run it when bumping a pinned version, review the diff, commit the result:

    python scripts/pin_agent_releases.py --codex 0.153.4 --opencode 1.18.18

Claude Code defaults to the build the installed Claude Agent SDK was released
with (its ``__cli_version__``), the version the daemon's Claude runner is
tested against; ``--claude`` overrides that, with a warning.

Everything comes from the vendor's own release metadata, the same sources
their install scripts verify against; nothing here downloads a binary:

- Claude Code: ``manifest.json`` of the version (binary name, SHA-256, size
  per platform).
- Codex: ``codex-package_SHA256SUMS`` of the release, plus a HEAD request per
  package for its size.
- OpenCode: the GitHub release of the tag, whose assets carry a SHA-256
  ``digest`` and size (OpenCode publishes no checksum file of its own).

Pinning the checksums in our code, rather than reading them at install time,
means a download is only accepted if it is byte for byte the build that was
pinned here.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from http.client import HTTPResponse
from pathlib import Path
from typing import Any, cast

USER_AGENT = "vicoa-agent-pin"
CLAUDE_BASE = "https://downloads.claude.ai/claude-code-releases"
CODEX_BASE = "https://releases.openai.com/codex/releases"
CODEX_GITHUB = "https://github.com/openai/codex/releases/download/rust-v{version}"
CODEX_TARGETS = [
    "aarch64-apple-darwin",
    "x86_64-apple-darwin",
    "aarch64-unknown-linux-musl",
    "x86_64-unknown-linux-musl",
    "aarch64-pc-windows-msvc",
    "x86_64-pc-windows-msvc",
]
OPENCODE_API = (
    "https://api.github.com/repos/anomalyco/opencode/releases/tags/v{version}"
)
OUT = Path(__file__).resolve().parent.parent / "src" / "vicoa" / "agent_releases.py"


def _get(url: str, method: str = "GET") -> HTTPResponse:
    request = urllib.request.Request(
        url, method=method, headers={"User-Agent": USER_AGENT}
    )
    return cast(HTTPResponse, urllib.request.urlopen(request, timeout=30))


def _json(url: str) -> Any:
    with _get(url) as response:
        return json.load(response)


def _text(url: str) -> str:
    with _get(url) as response:
        return response.read().decode()


def _size(url: str) -> int:
    with _get(url, method="HEAD") as response:
        return int(response.headers["Content-Length"])


def claude_assets(version: str) -> dict[str, dict[str, Any]]:
    manifest = _json(f"{CLAUDE_BASE}/{version}/manifest.json")
    assets: dict[str, dict[str, Any]] = {}
    for platform, entry in sorted(manifest["platforms"].items()):
        binary = entry["binary"]
        assets[platform] = {
            "url": f"{CLAUDE_BASE}/{version}/{platform}/{binary}",
            "sha256": str(entry["checksum"]).lower(),
            "size": int(entry["size"]),
            "archive": "raw",
            "binary": binary,
        }
    return assets


def codex_assets(version: str) -> dict[str, dict[str, Any]]:
    sums: dict[str, str] = {}
    for line in _text(f"{CODEX_BASE}/{version}/codex-package_SHA256SUMS").splitlines():
        parts = line.split()
        if len(parts) == 2:
            sums[parts[1]] = parts[0].lower()
    assets: dict[str, dict[str, Any]] = {}
    for target in CODEX_TARGETS:
        name = f"codex-package-{target}.tar.gz"
        url = f"{CODEX_BASE}/{version}/{name}"
        assets[target] = {
            "url": url,
            "fallback_url": f"{CODEX_GITHUB.format(version=version)}/{name}",
            "sha256": sums[name],
            "size": _size(url),
            "archive": "tar.gz",
            "binary": "bin/codex.exe" if "windows" in target else "bin/codex",
        }
    return assets


def opencode_assets(version: str) -> dict[str, dict[str, Any]]:
    release = _json(OPENCODE_API.format(version=version))
    assets: dict[str, dict[str, Any]] = {}
    for asset in release["assets"]:
        name: str = asset["name"]
        if not name.startswith("opencode-") or name.startswith("opencode-desktop"):
            continue
        for ext, archive in ((".tar.gz", "tar.gz"), (".zip", "zip")):
            if name.endswith(ext):
                key = name[len("opencode-") : -len(ext)]
                digest = str(asset.get("digest") or "")
                if not digest.startswith("sha256:"):
                    raise SystemExit(f"{name} has no SHA-256 digest on GitHub")
                assets[key] = {
                    "url": asset["browser_download_url"],
                    "sha256": digest.removeprefix("sha256:").lower(),
                    "size": int(asset["size"]),
                    "archive": archive,
                    "binary": "opencode.exe"
                    if key.startswith("windows")
                    else "opencode",
                }
    return dict(sorted(assets.items()))


def render(pins: dict[str, tuple[str, dict[str, dict[str, Any]]]]) -> str:
    lines = [
        '"""Agent CLI builds this daemon release may download. Generated; do not edit.',
        "",
        "Regenerate with ``scripts/pin_agent_releases.py`` when bumping a version.",
        "Each asset is the vendor's own build with the SHA-256 and size its release",
        "metadata publishes, so a download is accepted only if it is exactly that build.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from vicoa.agent_release_types import PinnedRelease, ReleaseAsset",
        "",
        "PINNED_RELEASES: dict[str, PinnedRelease] = {",
    ]
    # Vendor metadata becomes Python source: json.dumps quotes and escapes each
    # value, so a stray quote can't break or inject into the generated file.
    q = json.dumps
    for agent, (version, assets) in pins.items():
        lines.append(f"    {q(agent)}: PinnedRelease(")
        lines.append(f"        agent={q(agent)},")
        lines.append(f"        version={q(version)},")
        lines.append("        assets={")
        for key, a in assets.items():
            lines.append(f"            {q(key)}: ReleaseAsset(")
            lines.append(f"                url={q(a['url'])},")
            if a.get("fallback_url"):
                lines.append(f"                fallback_url={q(a['fallback_url'])},")
            lines.append(f"                sha256={q(a['sha256'])},")
            lines.append(f"                size={int(a['size'])},")
            lines.append(f"                archive={q(a['archive'])},")
            lines.append(f"                binary={q(a['binary'])},")
            lines.append("            ),")
        lines.append("        },")
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _sdk_claude_version() -> str | None:
    try:
        from claude_agent_sdk._cli_version import __cli_version__
    except ImportError:
        return None
    return str(__cli_version__)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--claude",
        help="Claude Code version (default: the installed SDK's own build)",
    )
    parser.add_argument("--codex", required=True, help="Codex version")
    parser.add_argument("--opencode", required=True, help="OpenCode (v1) version")
    args = parser.parse_args()
    sdk_claude = _sdk_claude_version()
    if args.claude is None:
        if sdk_claude is None:
            parser.error("claude_agent_sdk isn't installed here; pass --claude")
        args.claude = sdk_claude
    elif sdk_claude is not None and args.claude != sdk_claude:
        print(
            f"warning: pinning Claude Code {args.claude}, but the installed SDK "
            f"was released with {sdk_claude}"
        )
    pins = {
        "claude": (args.claude, claude_assets(args.claude)),
        "codex": (args.codex, codex_assets(args.codex)),
        "opencode": (args.opencode, opencode_assets(args.opencode)),
    }
    OUT.write_text(render(pins))
    for agent, (version, assets) in pins.items():
        print(f"{agent} {version}: {len(assets)} platforms")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
