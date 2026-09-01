"""The auth seam: agent keys, provider selection, and the two providers.

Deliberately database-free — the one DB touch (the API-key revocation lookup)
is injected so every branch is reachable without a container.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jose import jwt as jose_jwt
from jose.backends.cryptography_backend import CryptographyECKey, CryptographyRSAKey
from jose.constants import ALGORITHMS

from shared.auth import agent_tokens, builtin_provider, passwords, provider
from shared.auth.base import Principal, TokenVerificationError
from shared.auth.builtin_provider import BuiltinAuthProvider
from shared.auth.supabase_provider import SupabaseAuthProvider
from shared.config import settings

_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _RSA_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_PUBLIC_PEM = (
    _RSA_KEY.public_key()
    .public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)

_SUPABASE_SECRET = "test-supabase-hs256-secret"
_SUPABASE_URL = "https://project.supabase.co"

# Asymmetric signing keys, as a Supabase project has after migrating away from
# the legacy HS256 secret. The public halves become the JWKS the provider
# fetches; the private halves stand in for GoTrue signing the access token.
_EC_KEY = ec.generate_private_key(ec.SECP256R1())
_EC_PRIVATE_PEM = _EC_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_EC_KID = "ec-signing-key-1"
_EC_JWK = {
    **CryptographyECKey(_EC_KEY.public_key(), ALGORITHMS.ES256).to_dict(),
    "kid": _EC_KID,
    "use": "sig",
}
_RSA_KID = "rsa-signing-key-1"
_RSA_JWK = {
    **CryptographyRSAKey(_PUBLIC_PEM, ALGORITHMS.RS256).to_dict(),
    "kid": _RSA_KID,
    "use": "sig",
}


@pytest.fixture(autouse=True)
def _vicoa_keypair(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "jwt_private_key", _PRIVATE_PEM)
    monkeypatch.setattr(settings, "jwt_public_key", _PUBLIC_PEM)
    monkeypatch.setattr(settings, "enforce_api_key_revocation", False)
    agent_tokens.reset_revocation_cache()
    provider.reset_auth_provider()
    yield
    agent_tokens.reset_revocation_cache()
    provider.reset_auth_provider()


# --- agent keys --------------------------------------------------------------


def test_agent_key_round_trips_to_an_agent_principal() -> None:
    user_id = uuid4()
    token = agent_tokens.create_agent_jwt(str(user_id))

    result = agent_tokens.verify_agent_jwt(token)

    assert result == Principal(user_id=user_id, kind="agent")


def test_a_key_minted_before_the_typ_claim_is_still_accepted() -> None:
    """Every key in the wild predates `typ`; absence must mean "agent"."""
    user_id = uuid4()
    legacy = jose_jwt.encode({"sub": str(user_id)}, _PRIVATE_PEM, algorithm="RS256")

    assert agent_tokens.verify_agent_jwt(legacy).user_id == user_id


def test_a_user_session_is_not_usable_as_an_agent_key() -> None:
    token, _ = builtin_provider.create_session_token(uuid4())

    with pytest.raises(TokenVerificationError, match="not an agent key"):
        agent_tokens.verify_agent_jwt(token)


def test_an_agent_key_is_not_usable_as_a_user_session() -> None:
    token = agent_tokens.create_agent_jwt(str(uuid4()))

    with pytest.raises(TokenVerificationError, match="not a user session"):
        BuiltinAuthProvider().verify_user_token(token)


def test_an_expired_agent_key_is_rejected() -> None:
    expired = jose_jwt.encode(
        {"sub": str(uuid4()), "exp": int(time.time()) - 60},
        _PRIVATE_PEM,
        algorithm="RS256",
    )

    with pytest.raises(TokenVerificationError):
        agent_tokens.verify_agent_jwt(expired)


def test_a_key_signed_by_someone_else_is_rejected() -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    foreign = jose_jwt.encode(
        {"sub": str(uuid4())},
        other.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        algorithm="RS256",
    )

    with pytest.raises(TokenVerificationError):
        agent_tokens.verify_agent_jwt(foreign)


# --- revocation --------------------------------------------------------------


def test_a_revoked_key_stops_working(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enforce_api_key_revocation", True)
    monkeypatch.setattr(agent_tokens, "_api_key_is_live", lambda _db, _hash: False)
    token = agent_tokens.create_agent_jwt(str(uuid4()))

    with pytest.raises(TokenVerificationError, match="revoked"):
        agent_tokens.verify_agent_jwt(token, db=object())


def test_a_live_key_is_looked_up_once_then_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enforce_api_key_revocation", True)
    lookups: list[str] = []

    def _live(_db, token_hash: str) -> bool:
        lookups.append(token_hash)
        return True

    monkeypatch.setattr(agent_tokens, "_api_key_is_live", _live)
    token = agent_tokens.create_agent_jwt(str(uuid4()))

    agent_tokens.verify_agent_jwt(token, db=object())
    agent_tokens.verify_agent_jwt(token, db=object())

    assert lookups == [agent_tokens.get_token_hash(token)]


def test_revoking_a_key_drops_the_cached_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enforce_api_key_revocation", True)
    live = {"value": True}
    monkeypatch.setattr(
        agent_tokens, "_api_key_is_live", lambda _db, _hash: live["value"]
    )
    token = agent_tokens.create_agent_jwt(str(uuid4()))
    agent_tokens.verify_agent_jwt(token, db=object())

    live["value"] = False
    agent_tokens.reset_revocation_cache()

    with pytest.raises(TokenVerificationError):
        agent_tokens.verify_agent_jwt(token, db=object())


# --- built-in provider -------------------------------------------------------


def test_a_builtin_session_carries_identity() -> None:
    user_id = uuid4()
    token, expires_at = builtin_provider.create_session_token(
        user_id, "self@host.local", "Self Hoster"
    )

    result = BuiltinAuthProvider().verify_user_token(token)

    assert result.user_id == user_id
    assert result.kind == "user"
    assert result.email == "self@host.local"
    assert result.display_name == "Self Hoster"
    assert expires_at > builtin_provider._utc_now()


def test_a_session_signed_for_another_audience_is_rejected() -> None:
    token = jose_jwt.encode(
        {
            "sub": str(uuid4()),
            agent_tokens.TOKEN_TYPE_CLAIM: agent_tokens.USER_TOKEN_TYPE,
            "iss": builtin_provider.BUILTIN_ISSUER,
            "aud": "somewhere-else",
        },
        _PRIVATE_PEM,
        algorithm="RS256",
    )

    with pytest.raises(TokenVerificationError, match="audience"):
        BuiltinAuthProvider().verify_user_token(token)


def test_password_hashes_round_trip_and_reject_the_wrong_password() -> None:
    stored = passwords.hash_password("correct horse battery")

    assert passwords.verify_password("correct horse battery", stored)
    assert not passwords.verify_password("wrong horse battery", stored)
    assert not passwords.verify_password("anything", "not-a-hash")
    assert not passwords.needs_rehash(stored)


def test_a_short_password_is_refused() -> None:
    with pytest.raises(builtin_provider.WeakPassword):
        builtin_provider._assert_password_strength("short")


# --- Supabase provider (local verification) ----------------------------------


def _supabase_token(**overrides) -> str:
    claims = {
        "sub": str(uuid4()),
        "aud": "authenticated",
        "iss": f"{_SUPABASE_URL}/auth/v1",
        "exp": int(time.time()) + 3600,
        "email": "user@example.com",
        "user_metadata": {"display_name": "Example User"},
    }
    claims.update(overrides)
    return jose_jwt.encode(claims, _SUPABASE_SECRET, algorithm="HS256")


@pytest.fixture
def supabase_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "supabase_url", _SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "supabase_jwt_secret", _SUPABASE_SECRET)


def test_supabase_tokens_verify_locally(supabase_configured) -> None:
    user_id = uuid4()
    token = _supabase_token(sub=str(user_id))

    result = SupabaseAuthProvider().verify_user_token(token)

    assert result == Principal(
        user_id=user_id,
        kind="user",
        email="user@example.com",
        display_name="Example User",
    )


def test_a_supabase_token_from_another_project_is_rejected(
    supabase_configured,
) -> None:
    token = _supabase_token(iss="https://someone-else.supabase.co/auth/v1")

    with pytest.raises(TokenVerificationError, match="issued by"):
        SupabaseAuthProvider().verify_user_token(token)


def test_an_expired_supabase_token_is_rejected(supabase_configured) -> None:
    token = _supabase_token(exp=int(time.time()) - 60)

    with pytest.raises(TokenVerificationError):
        SupabaseAuthProvider().verify_user_token(token)


def test_a_supabase_token_with_the_wrong_audience_is_rejected(
    supabase_configured,
) -> None:
    token = _supabase_token(aud="anon")

    with pytest.raises(TokenVerificationError):
        SupabaseAuthProvider().verify_user_token(token)


def test_without_a_secret_local_verification_defers_to_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No key material must fall back, not fail — that is what keeps an
    existing deployment working before SUPABASE_JWT_SECRET is set."""
    monkeypatch.setattr(settings, "supabase_url", _SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    instance = SupabaseAuthProvider()
    called: list[str] = []

    def _remote(token: str) -> Principal:
        called.append(token)
        return Principal(user_id=uuid4())

    monkeypatch.setattr(instance, "_verify_over_network", _remote)
    token = _supabase_token()

    instance.verify_user_token(token)

    assert called == [token]


# --- Supabase provider (asymmetric / JWKS after signing-key migration) --------


def _supabase_asym_token(private_pem: str, alg: str, kid: str, **overrides) -> str:
    claims = {
        "sub": str(uuid4()),
        "aud": "authenticated",
        "iss": f"{_SUPABASE_URL}/auth/v1",
        "exp": int(time.time()) + 3600,
        "email": "user@example.com",
        "user_metadata": {"display_name": "Example User"},
    }
    claims.update(overrides)
    return jose_jwt.encode(claims, private_pem, algorithm=alg, headers={"kid": kid})


def test_supabase_es256_tokens_verify_via_jwks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After migrating to JWT signing keys, access tokens are ES256 and verified
    against the published JWKS. This path has no network fallback once the key is
    found, so it must work before the migration is switched on."""
    monkeypatch.setattr(settings, "supabase_url", _SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")  # mirrors prod today
    user_id = uuid4()
    token = _supabase_asym_token(_EC_PRIVATE_PEM, "ES256", _EC_KID, sub=str(user_id))

    instance = SupabaseAuthProvider()
    monkeypatch.setattr(
        instance, "_get_jwks", lambda *, force_refresh: {"keys": [_EC_JWK]}
    )

    result = instance.verify_user_token(token)

    assert result == Principal(
        user_id=user_id,
        kind="user",
        email="user@example.com",
        display_name="Example User",
    )


def test_supabase_rs256_tokens_verify_via_jwks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RSA signing keys are the other asymmetric option Supabase offers."""
    monkeypatch.setattr(settings, "supabase_url", _SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    user_id = uuid4()
    token = _supabase_asym_token(_PRIVATE_PEM, "RS256", _RSA_KID, sub=str(user_id))

    instance = SupabaseAuthProvider()
    monkeypatch.setattr(
        instance, "_get_jwks", lambda *, force_refresh: {"keys": [_RSA_JWK]}
    )

    result = instance.verify_user_token(token)

    assert result.user_id == user_id


def test_an_unknown_signing_key_defers_to_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token whose `kid` is not in the JWKS falls back rather than hard-fails —
    this is what keeps tokens signed by a rotated-out key working."""
    monkeypatch.setattr(settings, "supabase_url", _SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    token = _supabase_asym_token(_EC_PRIVATE_PEM, "ES256", "rotated-out-kid")

    instance = SupabaseAuthProvider()
    monkeypatch.setattr(instance, "_get_jwks", lambda *, force_refresh: {"keys": []})
    called: list[str] = []

    def _remote(tok: str) -> Principal:
        called.append(tok)
        return Principal(user_id=uuid4())

    monkeypatch.setattr(instance, "_verify_over_network", _remote)

    instance.verify_user_token(token)

    assert called == [token]


# --- provider selection ------------------------------------------------------


def test_the_provider_is_inferred_from_what_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_provider", "")
    monkeypatch.setattr(settings, "supabase_url", _SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    assert provider.resolve_auth_provider_name() == "supabase"

    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")
    assert provider.resolve_auth_provider_name() == "builtin"


def test_an_explicit_setting_wins_over_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_provider", "builtin")
    monkeypatch.setattr(settings, "supabase_url", _SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")

    assert provider.resolve_auth_provider_name() == "builtin"
    assert isinstance(provider.get_auth_provider(), BuiltinAuthProvider)


def test_an_unknown_provider_name_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_provider", "okta")

    with pytest.raises(RuntimeError, match="Unknown AUTH_PROVIDER"):
        provider.get_auth_provider()
