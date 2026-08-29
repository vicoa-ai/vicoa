"""Password hashing for the built-in auth provider.

Uses `hashlib.scrypt` from the standard library rather than bcrypt/argon2 so a
self-hosted build needs no extra wheel — this module is on the critical path of
the one flow (sign-in) a self-hoster hits before anything else works, and a
missing native dependency there is a bad first impression.

Stored format is self-describing so the cost parameters can be raised later
without invalidating existing hashes:

    scrypt$<n>$<r>$<p>$<salt-b64>$<derived-b64>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

# OWASP's scrypt baseline (n=2**15, r=8, p=1) — ~32 MB and ~50 ms per hash on
# commodity hardware, which is the point: it is what makes an offline attack on
# a stolen `user_credentials` table expensive.
_N = 2**15
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16
_SCHEME = "scrypt"

# hashlib.scrypt refuses to allocate more than `maxmem`, and its default (32 MB)
# sits exactly on the boundary of what n=2**15, r=8 needs.
_MAXMEM = 128 * _N * _R * 2


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage."""
    if not password:
        raise ValueError("password must not be empty")
    salt = os.urandom(_SALT_BYTES)
    derived = _derive(password, salt, _N, _R, _P)
    return "$".join([_SCHEME, str(_N), str(_R), str(_P), _b64(salt), _b64(derived)])


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a plaintext password against a stored hash.

    Returns False (rather than raising) for malformed stored values so that a
    corrupted row reads as "wrong password" instead of a 500 that tells an
    attacker the account exists.
    """
    try:
        scheme, n, r, p, salt_b64, derived_b64 = stored.split("$")
        if scheme != _SCHEME:
            return False
        salt = _unb64(salt_b64)
        expected = _unb64(derived_b64)
        candidate = _derive(password, salt, int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored: str) -> bool:
    """Whether `stored` was made with weaker parameters than today's defaults."""
    try:
        scheme, n, r, p, _salt, _derived = stored.split("$")
    except ValueError:
        return True
    return scheme != _SCHEME or (int(n), int(r), int(p)) != (_N, _R, _P)


def _derive(
    password: str, salt: bytes, n: int, r: int, p: int, dklen: int = _DKLEN
) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=dklen,
        maxmem=max(_MAXMEM, 128 * n * r * 2),
    )


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))
