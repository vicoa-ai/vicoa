#!/usr/bin/env python3
"""Post one version's changelog section to a Discord channel webhook.

    DISCORD_WEBHOOK_URL=... python3 .github/scripts/discord_release_post.py \
        apps/web/content/docs/changelog/desktop-app.mdx 0.1.32 \
        [--title "Vicoa desktop"] [--note "How to get it"] [--dry-run]

Reads the `### v<version>` section of a docs changelog (the user-facing notes,
not the commit list in the GitHub release body) and posts it as one embed that
links back to that section on the docs site. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

SITE = os.environ.get("VICOA_SITE_URL", "https://vicoa.ai").rstrip("/")
EMBED_DESCRIPTION_LIMIT = 4096
EMBED_COLOR = 0x3B82F6
DEFAULT_NOTE = f"Already installed? The app updates itself. New here? [Download]({SITE}/download)"


def read_section(changelog: Path, version: str) -> tuple[str | None, list[str]]:
    """Return (date line, bullet lines) of `### v<version>`."""
    text = changelog.read_text()
    m = re.search(rf"^### v{re.escape(version)}[ \t]*\n(.*?)(?=^#{{1,3}} |\Z)", text, re.M | re.S)
    if not m:
        sys.exit(f"{changelog}: no '### v{version}' section")
    lines = [line.rstrip() for line in m.group(1).strip().splitlines() if line.strip()]
    date = lines[0] if lines and not lines[0].startswith("-") else None
    bullets = [line for line in lines if line.startswith("- ")]
    if not bullets:
        sys.exit(f"{changelog}: '### v{version}' has no bullets")
    return date, bullets


def absolute_links(line: str) -> str:
    # Docs links are site-relative (`](/docs/...)`); Discord needs absolute URLs.
    return re.sub(r"\]\(/", f"]({SITE}/", line)


def build_payload(changelog: Path, version: str, title: str, note: str = DEFAULT_NOTE) -> dict[str, Any]:
    date, bullets = read_section(changelog, version)
    page = f"{SITE}/docs/changelog/{changelog.stem}#v{version.replace('.', '')}"
    footer = f"\n\n{note}\n[Full changelog]({page})"
    body: list[str] = []
    for n, bullet in enumerate(bullets):
        line = absolute_links(bullet)
        rest = len(bullets) - n
        more = f"\n…and {rest} more" if rest > 1 else ""
        if len("\n".join([*body, line])) + len(more) + len(footer) > EMBED_DESCRIPTION_LIMIT:
            body.append(f"…and {rest} more")
            break
        body.append(line)
    embed: dict[str, Any] = {
        "title": f"{title} v{version}",
        "url": page,
        "description": "\n".join(body) + footer,
        "color": EMBED_COLOR,
    }
    if date:
        embed["footer"] = {"text": date}
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


def post(url: str, payload: dict[str, Any]) -> None:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "vicoa-release (https://github.com/vicoa-ai/vicoa)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"Posted to Discord: HTTP {resp.status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("changelog", type=Path)
    parser.add_argument("version", help="version without the leading v, e.g. 0.1.32")
    parser.add_argument("--title", default="Vicoa desktop")
    parser.add_argument("--note", default=DEFAULT_NOTE, help="line above the changelog link: how to get this version")
    parser.add_argument("--dry-run", action="store_true", help="print the payload instead of posting")
    args = parser.parse_args()

    payload = build_payload(args.changelog, args.version.lstrip("v"), args.title, args.note)
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        sys.exit("DISCORD_WEBHOOK_URL is not set")
    post(url, payload)


if __name__ == "__main__":
    main()
