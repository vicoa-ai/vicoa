"""Shared HTTP scaffolding for authenticated ``vicoa`` CLI subcommands.

Talks to the agent-facing server (``agents.vicoa.ai``) with the same Bearer API
key every ``vicoa`` command uses. Extracted so read-only inspection commands
(``vicoa session ...``) share one auth + request path instead of each
re-implementing it. ``vicoa task`` predates this helper and keeps its own copy.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

from vicoa.constants import DEFAULT_API_URL


def resolve_api_key(args) -> str:
    """Resolve the API key without ever popping a browser.

    Agents run non-interactively, so unlike ``ensure_api_key`` this fails fast
    with an actionable message instead of launching the OAuth flow.
    """
    key = (
        getattr(args, "api_key", None)
        or os.environ.get("VICOA_API_KEY")
        or _load_stored_api_key()
    )
    if not key:
        print(
            "No Vicoa API key found. Set VICOA_API_KEY, pass --api-key, "
            "or run `vicoa --auth` first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def _load_stored_api_key() -> Optional[str]:
    # Deferred import: cli.py imports command modules at load time, so importing
    # it at module load time would be circular.
    from vicoa.cli import load_stored_api_key

    return load_stored_api_key()


def _client(args, api_key: str):
    from vicoa.sdk.client import VicoaClient

    base_url = getattr(args, "base_url", None) or DEFAULT_API_URL
    return VicoaClient(api_key=api_key, base_url=base_url)


def request(
    args,
    api_key: str,
    method: str,
    endpoint: str,
    *,
    params: Optional[dict] = None,
    json: Optional[dict] = None,
) -> Any:
    """Make one authenticated request, turning failures into clean CLI exits.

    Goes through the SDK client's configured session (retries, auth header,
    timeout). Returns ``None`` for empty/204 responses, the decoded JSON
    otherwise. Any transport error, 401, or non-2xx exits the process with an
    actionable message on stderr.
    """
    from urllib.parse import urljoin

    import requests

    try:
        with _client(args, api_key) as client:
            resp = client.session.request(
                method,
                urljoin(client.base_url, endpoint),
                params=params,
                json=json,
                timeout=client.timeout,
            )
    except requests.exceptions.Timeout:
        print("Error: request to the Vicoa server timed out.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        print(f"Error: could not reach the Vicoa server ({exc}).", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 401:
        print(
            "Authentication failed. Your API key may be invalid or expired; "
            "run `vicoa --reauth`.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        print(f"Error: {detail} (HTTP {resp.status_code})", file=sys.stderr)
        sys.exit(1)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()
