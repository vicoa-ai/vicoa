"""Unit tests for the upgrade-only, user-pinned RevenueCat reconcile path.

Covers the guarantees added for the generic `POST /billing/mobile/reconcile`
endpoint — Fix B for the RevenueCat "transfer to new App User ID" gap, where a
restore under a second Vicoa account leaves the transferred entitlement stranded
on the old account (the TRANSFER webhook is dropped by the handler):

  * ``sync_subscription_status(..., target_user_id=uid)`` pins the grant to the
    authenticated user and never re-resolves RC's (stale) original_app_user_id
    alias — the exact bug that re-attributed the sub to the wrong account.
  * ``allow_downgrade=False`` makes reconcile strictly upgrade-only: it can
    never stomp a Stripe/other-provider plan or downgrade on a stale RC read.
  * ``allow_downgrade=True`` (the webhook default) still downgrades on expiry,
    and the webhook path still resolves the user from original_app_user_id.

Pure unit tests: ``get_or_create_subscription`` / ``resolve_and_ensure_app_user``
/ ``fetch_subscriber_from_revenuecat`` are monkeypatched, so there is no DB or
network dependency and they run under ``make test-unit``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import backend.api.mobile_billing as mb


class _FakeDB:
    def commit(self) -> None:  # noqa: D401 - trivial stub
        pass

    def rollback(self) -> None:
        pass


def _sub(**kw):
    base = dict(
        user_id=None,
        plan_type="free",
        agent_limit=10,
        provider=None,
        provider_customer_id=None,
        provider_subscription_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _subscriber(
    pro: bool, *, expires="2999-01-01T00:00:00Z", store="app_store", txn="TXN1"
):
    """Shape a RevenueCat /subscribers response. `original_app_user_id` is a
    deliberately stale anonymous alias, so a test that ends up attributed to it
    (instead of the pinned target) fails loudly."""
    subscriber = {
        "original_app_user_id": "$RCAnonymousID:staleAlias",
        "entitlements": {},
        "subscriptions": {},
        "management_url": None,
    }
    if pro:
        subscriber["entitlements"] = {"pro": {"expires_date": expires}}
        subscriber["subscriptions"] = {
            "p": {"expires_date": expires, "store": store, "store_transaction_id": txn}
        }
    return {"subscriber": subscriber}


def _patch_get_or_create(monkeypatch, row) -> None:
    monkeypatch.setattr(mb, "get_or_create_subscription", lambda uid, db: row)


def _forbid_resolve(monkeypatch) -> None:
    def _boom(*_a, **_k):
        raise AssertionError(
            "resolve_and_ensure_app_user must not be called when target_user_id is set"
        )

    monkeypatch.setattr(mb, "resolve_and_ensure_app_user", _boom)


# --------------------------------------------------------------------------- #
# sync_subscription_status: pinning + upgrade-only semantics
# --------------------------------------------------------------------------- #


def test_grant_pins_to_target_user_not_stale_alias(monkeypatch) -> None:
    uid = uuid4()
    row = _sub(user_id=uid)
    _patch_get_or_create(monkeypatch, row)
    _forbid_resolve(monkeypatch)

    ok = mb.sync_subscription_status(
        _subscriber(pro=True), _FakeDB(), allow_downgrade=False, target_user_id=uid
    )

    assert ok is True
    assert row.plan_type == "pro"
    assert row.agent_limit == -1
    assert row.provider == "apple"
    # Pinned to the asking user — NOT RC's original_app_user_id alias.
    assert row.provider_customer_id == str(uid)
    assert row.provider_subscription_id == "TXN1"


def test_upgrade_only_never_downgrades_existing_plan(monkeypatch) -> None:
    """The critical safety property: a Stripe pro user with no RC entitlement
    must keep their plan when the reconcile fetches an empty RC subscriber."""
    uid = uuid4()
    row = _sub(
        user_id=uid,
        plan_type="pro",
        agent_limit=-1,
        provider="stripe",
        provider_customer_id="cus_ABC",
        provider_subscription_id="sub_ABC",
    )
    _patch_get_or_create(monkeypatch, row)
    _forbid_resolve(monkeypatch)

    ok = mb.sync_subscription_status(
        _subscriber(pro=False), _FakeDB(), allow_downgrade=False, target_user_id=uid
    )

    assert ok is True
    assert row.plan_type == "pro"
    assert row.provider == "stripe"
    assert row.provider_customer_id == "cus_ABC"
    assert row.provider_subscription_id == "sub_ABC"


def test_expired_entitlement_is_not_treated_as_active(monkeypatch) -> None:
    """An entitlement whose expires_date is in the past must not grant pro."""
    uid = uuid4()
    row = _sub(user_id=uid)
    _patch_get_or_create(monkeypatch, row)
    _forbid_resolve(monkeypatch)

    ok = mb.sync_subscription_status(
        _subscriber(pro=True, expires="2000-01-01T00:00:00Z"),
        _FakeDB(),
        allow_downgrade=False,
        target_user_id=uid,
    )

    assert ok is True
    assert row.plan_type == "free"  # unchanged; upgrade-only + expired == no grant


def test_webhook_default_downgrades_on_expiry(monkeypatch) -> None:
    uid = uuid4()
    row = _sub(user_id=uid, plan_type="pro", agent_limit=-1, provider="apple")
    _patch_get_or_create(monkeypatch, row)
    _forbid_resolve(monkeypatch)

    # allow_downgrade defaults to True (webhook behaviour).
    ok = mb.sync_subscription_status(
        _subscriber(pro=False), _FakeDB(), target_user_id=uid
    )

    assert ok is True
    assert row.plan_type == "free"
    assert row.provider is None


def test_webhook_path_resolves_original_app_user_id(monkeypatch) -> None:
    """With no target_user_id (the webhook path) the user is resolved from
    original_app_user_id and provider_customer_id is that id."""
    uid = uuid4()
    row = _sub(user_id=uid)
    _patch_get_or_create(monkeypatch, row)
    seen = {}

    def _resolve(app_user_id, _db):
        seen["id"] = app_user_id
        return uid

    monkeypatch.setattr(mb, "resolve_and_ensure_app_user", _resolve)

    sub = _subscriber(pro=True)
    sub["subscriber"]["original_app_user_id"] = str(uid)  # webhook form: real UUID
    ok = mb.sync_subscription_status(sub, _FakeDB())  # target=None, downgrade=True

    assert ok is True
    assert seen["id"] == str(uid)
    assert row.plan_type == "pro"
    assert row.provider_customer_id == str(uid)


# --------------------------------------------------------------------------- #
# reconcile_revenuecat_subscription
# --------------------------------------------------------------------------- #


def test_reconcile_rc_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(mb, "REVENUECAT_API_KEY", "")

    async def _fetch(_):
        raise AssertionError("must not hit RevenueCat when the key is missing")

    monkeypatch.setattr(mb, "fetch_subscriber_from_revenuecat", _fetch)

    granted, detail = asyncio.run(
        mb.reconcile_revenuecat_subscription(SimpleNamespace(id=uuid4()), _FakeDB())
    )
    assert granted is False
    assert detail == "revenuecat_not_configured"


def test_reconcile_rc_no_subscriber(monkeypatch) -> None:
    monkeypatch.setattr(mb, "REVENUECAT_API_KEY", "sk_test")

    async def _fetch(_):
        return None

    monkeypatch.setattr(mb, "fetch_subscriber_from_revenuecat", _fetch)

    granted, detail = asyncio.run(
        mb.reconcile_revenuecat_subscription(SimpleNamespace(id=uuid4()), _FakeDB())
    )
    assert granted is False
    assert detail == "no_revenuecat_subscriber"


def test_reconcile_rc_grants_pro_to_current_user(monkeypatch) -> None:
    uid = uuid4()
    row = _sub(user_id=uid)
    _patch_get_or_create(monkeypatch, row)
    _forbid_resolve(monkeypatch)
    monkeypatch.setattr(mb, "REVENUECAT_API_KEY", "sk_test")

    async def _fetch(app_user_id):
        assert app_user_id == str(uid)  # fetched by the caller's own id
        return _subscriber(pro=True)

    monkeypatch.setattr(mb, "fetch_subscriber_from_revenuecat", _fetch)

    granted, detail = asyncio.run(
        mb.reconcile_revenuecat_subscription(SimpleNamespace(id=uid), _FakeDB())
    )
    assert granted is True
    assert detail == "granted"
    assert row.plan_type == "pro"
    assert row.provider_customer_id == str(uid)


def test_reconcile_rc_no_active_entitlement_leaves_free(monkeypatch) -> None:
    uid = uuid4()
    row = _sub(user_id=uid, plan_type="free")
    _patch_get_or_create(monkeypatch, row)
    _forbid_resolve(monkeypatch)
    monkeypatch.setattr(mb, "REVENUECAT_API_KEY", "sk_test")

    async def _fetch(_):
        return _subscriber(pro=False)

    monkeypatch.setattr(mb, "fetch_subscriber_from_revenuecat", _fetch)

    granted, detail = asyncio.run(
        mb.reconcile_revenuecat_subscription(SimpleNamespace(id=uid), _FakeDB())
    )
    assert granted is False
    assert detail == "no_active_entitlement"
    assert row.plan_type == "free"


# --------------------------------------------------------------------------- #
# reconcile_user_subscription (endpoint core): composes both legs
# --------------------------------------------------------------------------- #


def test_reconcile_user_subscription_composes_both_legs(monkeypatch) -> None:
    uid = uuid4()
    row = _sub(user_id=uid, plan_type="pro")
    _patch_get_or_create(monkeypatch, row)
    monkeypatch.setattr(mb, "apply_superwall_orphan_events", lambda u, db: (False, []))

    async def _rc(_u, _db):
        return (True, "granted")

    monkeypatch.setattr(mb, "reconcile_revenuecat_subscription", _rc)

    out = asyncio.run(
        mb.reconcile_user_subscription(SimpleNamespace(id=uid), _FakeDB())
    )

    assert out["status"] == "reconciled"
    assert out["plan_type"] == "pro"
    assert out["applied_events"] == []
    assert out["superwall_granted"] is False
    assert out["revenuecat"] == {"granted": True, "detail": "granted"}
