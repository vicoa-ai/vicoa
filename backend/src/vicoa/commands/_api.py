"""Shared HTTP scaffolding for authenticated ``vicoa`` CLI subcommands.

Talks to the agent-facing server (``agents.vicoa.ai``) with the same Bearer API
key every ``vicoa`` command uses. Extracted so the management commands
(``vicoa session|task|project|label|agent ...``) share one auth + request path
instead of each re-implementing it.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

from vicoa.constants import DEFAULT_API_URL


class RequestError(Exception):
    """A non-2xx reply, for callers that asked ``request`` not to exit.

    A bulk verb (``vicoa task update A B C``) must report one failed ref and
    carry on with the rest; the default exit-on-error is right for every
    single-shot command and wrong for that one.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"{detail} (HTTP {status_code})")
        self.status_code = status_code
        self.detail = detail


def resolve_api_key(args) -> str:
    """Resolve the API key without ever popping a browser.

    Agents run non-interactively, so unlike ``ensure_api_key`` this fails fast
    with an actionable message instead of launching the OAuth flow.
    """
    base_url = getattr(args, "base_url", None) or DEFAULT_API_URL
    key = (
        getattr(args, "api_key", None)
        or os.environ.get("VICOA_API_KEY")
        or _load_stored_api_key(base_url)
    )
    if not key:
        print(
            "No Vicoa API key found. Set VICOA_API_KEY, pass --api-key, "
            "or run `vicoa --auth` first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def _load_stored_api_key(base_url: Optional[str] = None) -> Optional[str]:
    # Deferred import: cli.py imports command modules at load time, so importing
    # it at module load time would be circular.
    from vicoa.cli import load_stored_api_key

    return load_stored_api_key(base_url)


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
    raise_on_error: bool = False,
) -> Any:
    """Make one authenticated request, turning failures into clean CLI exits.

    Goes through the SDK client's configured session (retries, auth header,
    timeout). Returns ``None`` for empty/204 responses, the decoded JSON
    otherwise. Any transport error, 401, or non-2xx exits the process with an
    actionable message on stderr — except that with ``raise_on_error`` a
    non-2xx (other than 401) raises :class:`RequestError` instead, for loops
    that want to keep going.
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
        if raise_on_error:
            raise RequestError(resp.status_code, str(detail))
        print(f"Error: {detail} (HTTP {resp.status_code})", file=sys.stderr)
        sys.exit(1)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()
