"""Pure unit tests: checkout must never hand Stripe a non-Stripe customer id.

Regression cover for Sentry PYTHON-FLASK-2P — `InvalidRequestError: No such
customer: '<uuid>'` on /api/v1/billing/checkout, 5 distinct users between
2026-06-27 and 2026-07-17.

`subscriptions.provider_customer_id` is overloaded by provider: a Stripe row
holds a `cus_…`, a mobile row holds RevenueCat's `app_user_id` (a UUID). The
checkout handler read it unconditionally and passed it to Stripe as `customer`,
so any Apple/Google subscriber trying to buy on the Stripe rail got a 500 —
which surfaced in the browser as a bogus CORS error, because Starlette's error
handler sits outside CORSMiddleware.

No DB, no network: the guard is a pure function over the row.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.api.billing import _existing_stripe_customer_id


@dataclass
class _Row:
    """Just the two fields the guard reads."""

    provider: str | None
    provider_customer_id: str | None


def test_apple_row_never_yields_a_stripe_customer() -> None:
    """The exact shape that broke prod: an Apple row whose customer id is a
    RevenueCat app_user_id. Returning it would send a UUID to Stripe."""
    row = _Row(
        provider="apple", provider_customer_id="dc488544-7a7f-4aa3-acdb-84755d472b38"
    )
    assert _existing_stripe_customer_id(row) is None


def test_google_row_never_yields_a_stripe_customer() -> None:
    row = _Row(
        provider="google", provider_customer_id="8de0c277-d462-af89-1234-26780ff79a23"
    )
    assert _existing_stripe_customer_id(row) is None


def test_stripe_row_reuses_its_customer() -> None:
    """The happy path must still reuse the customer rather than minting a new
    one on every checkout."""
    row = _Row(provider="stripe", provider_customer_id="cus_ABC123")
    assert _existing_stripe_customer_id(row) == "cus_ABC123"


def test_fresh_free_row_yields_none() -> None:
    """Never paid: nothing to reuse, so the caller creates a customer."""
    assert (
        _existing_stripe_customer_id(_Row(provider=None, provider_customer_id=None))
        is None
    )


def test_stripe_row_with_empty_customer_yields_none() -> None:
    """Empty string must not be treated as a usable customer id."""
    assert (
        _existing_stripe_customer_id(_Row(provider="stripe", provider_customer_id=""))
        is None
    )


def test_guard_matches_the_portal_and_webhook_conventions() -> None:
    """The portal (:292) and webhook (:518) both gate on provider == 'stripe'.
    Checkout was the only path that didn't; keep the three consistent."""
    for provider in ("apple", "google", "paddle", None):
        row = _Row(
            provider=provider, provider_customer_id="cus_LOOKS_REAL_BUT_WRONG_OWNER"
        )
        assert _existing_stripe_customer_id(row) is None, provider
