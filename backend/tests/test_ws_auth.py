"""Behavioral tests for WS subprotocol credential parsing (websocket-migration §2.9).

Tokens reach `/ws` through the `Sec-WebSocket-Protocol` header. Browsers require
the server to echo back exactly one offered subprotocol, and it must never echo
the credential-bearing value — so the client also offers a non-credential marker
(`vicoa-ws`) for the server to echo.
"""

import pytest

from shared.auth.ws import (
    WsAuthError,
    is_origin_allowed,
    parse_ws_subprotocol_credentials,
)


def test_parses_supabase_subprotocol_credentials() -> None:
    creds = parse_ws_subprotocol_credentials(["vicoa-ws", "vicoa-supabase.abc.def.ghi"])

    assert creds.token_type == "vicoa-supabase"
    assert creds.raw_token == "abc.def.ghi"
    assert creds.echo_subprotocol == "vicoa-ws"


def test_parses_api_key_subprotocol_credentials() -> None:
    creds = parse_ws_subprotocol_credentials(["vicoa-ws", "vicoa-key.rs256.jwt"])

    assert creds.token_type == "vicoa-key"
    assert creds.raw_token == "rs256.jwt"
    assert creds.echo_subprotocol == "vicoa-ws"


def test_raises_when_credential_subprotocol_has_empty_token() -> None:
    with pytest.raises(WsAuthError):
        parse_ws_subprotocol_credentials(["vicoa-ws", "vicoa-supabase."])


def test_raises_when_no_credential_subprotocol_offered() -> None:
    with pytest.raises(WsAuthError):
        parse_ws_subprotocol_credentials(["vicoa-ws"])


def test_raises_when_no_subprotocols_offered() -> None:
    with pytest.raises(WsAuthError):
        parse_ws_subprotocol_credentials([])


def test_echo_subprotocol_is_none_when_marker_not_offered() -> None:
    creds = parse_ws_subprotocol_credentials(["vicoa-supabase.abc"])

    assert creds.token_type == "vicoa-supabase"
    assert creds.echo_subprotocol is None


def test_unrecognized_non_credential_subprotocol_is_never_echoed() -> None:
    """Only the known marker may be echoed — never an arbitrary client value."""
    creds = parse_ws_subprotocol_credentials(["attacker-proto", "vicoa-supabase.abc"])

    assert creds.echo_subprotocol is None


def test_browser_origin_must_be_on_the_allowlist() -> None:
    allowed = ["https://vicoa.ai", "https://vibecodeanywhere.com"]

    assert is_origin_allowed("https://vicoa.ai", allowed) is True
    assert is_origin_allowed("https://evil.example", allowed) is False


def test_absent_origin_is_exempt_from_the_allowlist() -> None:
    """Native apps and daemons send no browser Origin header — there is no
    malicious-site vector for them, so a missing Origin is allowed (§2.9)."""
    assert is_origin_allowed(None, ["https://vicoa.ai"]) is True


def test_localhost_origin_is_allowed_for_the_desktop_app() -> None:
    """The desktop app's Electron renderer connects from a dynamic loopback
    port (http://127.0.0.1:<port>), which can't be a static allowlist entry.
    A remote page can't forge a loopback Origin and the token is still
    required, so any localhost/127.0.0.1 port is accepted."""
    allowed = ["https://vicoa.ai"]
    assert is_origin_allowed("http://127.0.0.1:57416", allowed) is True
    assert is_origin_allowed("http://localhost:3000", allowed) is True
    assert is_origin_allowed("http://127.0.0.1", allowed) is True
    # Not a loopback origin, not on the allowlist → still rejected.
    assert is_origin_allowed("http://127.0.0.1.evil.example", allowed) is False
    assert is_origin_allowed("https://evil.example", allowed) is False
