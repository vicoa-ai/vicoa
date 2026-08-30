"""Integration: /machines/register dedups a machine on (user_id, hardware_id).

The client-derived ``machine_id`` folds in the API key, so a re-auth (new key)
mints a different id. Registering with a stable ``hardware_id`` must resolve to
the SAME machine row instead of provisioning a duplicate. These hit a real DB,
so they are marked ``integration``.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from servers.api.models import RegisterMachineRequest
from servers.api.routers import register_machine_endpoint
from shared.database.models import Machine, User
from shared.database.session import SessionLocal

pytestmark = pytest.mark.integration


@pytest.fixture
def web_user() -> Iterator[UUID]:
    user_id = uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{user_id}@test.vicoa", display_name="t"))
        db.commit()
    try:
        yield user_id
    finally:
        with SessionLocal() as db:
            db.query(Machine).filter(Machine.user_id == user_id).delete()
            db.query(User).filter(User.id == user_id).delete()
            db.commit()


def _register(user_id: UUID, *, machine_id: str | None, hardware_id: str | None):
    with SessionLocal() as db:
        return register_machine_endpoint(
            request=RegisterMachineRequest(
                machine_id=machine_id, hardware_id=hardware_id, hostname="h"
            ),
            user_id=str(user_id),
            db=db,
        )


def _machine_count(user_id: UUID) -> int:
    with SessionLocal() as db:
        return db.query(Machine).filter(Machine.user_id == user_id).count()


def test_reauth_same_hardware_returns_same_machine(web_user: UUID) -> None:
    """Two registrations from one host with DIFFERENT client machine_ids (as a
    re-auth produces) resolve to the same machine via (user_id, hardware_id)."""
    user_id = web_user
    first = _register(user_id, machine_id=str(uuid4()), hardware_id="HW-abc")
    second = _register(user_id, machine_id=str(uuid4()), hardware_id="HW-abc")

    assert first.machine_id == second.machine_id
    assert _machine_count(user_id) == 1


def test_different_hardware_creates_distinct_machines(web_user: UUID) -> None:
    """Same user, two physical hosts → two machines."""
    user_id = web_user
    a = _register(user_id, machine_id=str(uuid4()), hardware_id="HW-1")
    b = _register(user_id, machine_id=str(uuid4()), hardware_id="HW-2")

    assert a.machine_id != b.machine_id
    assert _machine_count(user_id) == 2


def test_null_hardware_id_falls_back_to_machine_id(web_user: UUID) -> None:
    """Legacy daemons omit hardware_id: dedup is skipped and the supplied
    machine_id is honored as before (no partial-index collision on NULLs)."""
    user_id = web_user
    mid = str(uuid4())
    first = _register(user_id, machine_id=mid, hardware_id=None)
    second = _register(user_id, machine_id=mid, hardware_id=None)

    assert first.machine_id == mid == second.machine_id
    assert _machine_count(user_id) == 1


def test_cross_user_machine_id_mints_fresh_row(web_user: UUID) -> None:
    """A machine_id owned by ANOTHER account must not 403 — that propagates
    through the daemon's register_machine and crashes it, blocking desktop
    setup. Registering under the current user with a foreign (stale) id drops
    the id and mints a fresh row; the other user's row is left untouched and is
    never adopted."""
    current_user = web_user
    other_user = uuid4()
    foreign_id = str(uuid4())
    with SessionLocal() as db:
        db.add(User(id=other_user, email=f"{other_user}@test.vicoa", display_name="o"))
        db.commit()
    try:
        # other_user first registers this host and owns `foreign_id`.
        other = _register(other_user, machine_id=foreign_id, hardware_id=None)
        assert other.machine_id == foreign_id

        # current_user (e.g. after an account switch) registers with the stale
        # id still cached from the previous account.
        resp = _register(current_user, machine_id=foreign_id, hardware_id=None)

        # A fresh row was minted for current_user; the foreign id was not reused.
        assert resp.machine_id != foreign_id
        assert _machine_count(current_user) == 1

        # The other account's machine row is intact and still owned by them.
        with SessionLocal() as db:
            row = db.query(Machine).filter(Machine.id == UUID(foreign_id)).one()
            assert str(row.user_id) == str(other_user)
    finally:
        with SessionLocal() as db:
            db.query(Machine).filter(Machine.user_id == other_user).delete()
            db.query(User).filter(User.id == other_user).delete()
            db.commit()
