"""Per-client rate limiting for unauthenticated endpoints (collaboration §10.5).

The backend had no rate limiting before the public share router: every other
route sits behind a bearer token, so abuse was an account problem. A public
token-in-URL endpoint has no account to suspend, so the only knob is the
caller's address.

A token bucket per key, in process memory. That is deliberately the simple
version: `backend` runs several workers, so a client gets N buckets rather
than one, and a restart forgets everything — both fine for what this guards
against (a scraper or a runaway poller hammering one process), and it needs
no Redis. The bucket table is bounded LRU so an address-rotating attacker
cannot grow it without limit.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import HTTPException, Request

from shared.config import settings


@dataclass
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    """`rate` tokens per second refill, `burst` capacity, per key."""

    def __init__(self, rate: float, burst: int, *, max_keys: int = 50_000) -> None:
        if rate <= 0 or burst <= 0:
            raise ValueError("rate and burst must be positive")
        self.rate = rate
        self.burst = burst
        self.max_keys = max_keys
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def acquire(self, key: str, cost: float = 1.0) -> float | None:
        """Take `cost` tokens for `key`. Returns None when allowed, otherwise
        the number of seconds until enough tokens will have refilled."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(self.burst), updated=now)
                self._buckets[key] = bucket
                if len(self._buckets) > self.max_keys:
                    self._buckets.popitem(last=False)
            else:
                elapsed = max(0.0, now - bucket.updated)
                bucket.tokens = min(
                    float(self.burst), bucket.tokens + elapsed * self.rate
                )
                bucket.updated = now
                self._buckets.move_to_end(key)
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return None
            return (cost - bucket.tokens) / self.rate

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


def client_ip(request: Request) -> str:
    """The caller's address as the rate-limit key.

    Behind Fly's edge the socket peer is the proxy, and the real address is in
    `Fly-Client-IP` (set by the edge, not forwardable by a client). Which header
    to trust is configuration — `CLIENT_IP_HEADER` — because a self-hosted
    deployment behind its own reverse proxy uses a different one, and one with
    no proxy at all must trust none (a client could send any header it likes).
    """
    header = settings.client_ip_header.strip()
    if header:
        value = request.headers.get(header)
        if value:
            # X-Forwarded-For style lists: the first hop is the client.
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# One limiter for the whole public share surface. Sized for a viewer that
# polls every 5 s across a few tabs plus an image-heavy transcript loading its
# attachments in one burst — and far below what a scraper wants.
public_share_limiter = TokenBucketLimiter(
    rate=settings.public_share_rate_per_minute / 60.0,
    burst=settings.public_share_burst,
)


async def public_share_rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 with Retry-After once a client's bucket is dry."""
    retry_in = public_share_limiter.acquire(client_ip(request))
    if retry_in is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(max(1, int(retry_in + 0.999)))},
        )
