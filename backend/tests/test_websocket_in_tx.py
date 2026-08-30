"""Behavioral tests for the post-commit guarantee (websocket-migration plan §2.7).

`after_commit(db, cb)` attaches a one-shot listener to a SQLAlchemy session;
it fires after the next successful commit on that session and never after a
rollback. Both behaviours are exercised here against sync and async sessions.

The test surface is small on purpose: the heavy-lifting (listener registration,
once-only semantics, fire-on-commit timing) lives in SQLAlchemy itself. Our
wrapper adds two things worth testing: the AsyncSession adapter, and the
exception-swallowing inside `_fire` so a broken broadcast cannot poison
SQLAlchemy's event dispatch.
"""

import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.websocket.in_tx import after_commit


AnySession = Session | AsyncSession


@dataclass
class Variant:
    """Per-variant adapter so each behaviour can be written once."""

    name: str
    session: Callable[[], AbstractAsyncContextManager[AnySession]]
    commit: Callable[[AnySession], Awaitable[None]]
    rollback: Callable[[AnySession], Awaitable[None]]
    write_one: Callable[[AnySession], Awaitable[None]]


@asynccontextmanager
async def _sync_session() -> AsyncGenerator[AnySession, None]:
    engine = create_engine("sqlite://")
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


async def _sync_commit(session: AnySession) -> None:
    assert isinstance(session, Session)
    session.commit()


async def _sync_rollback(session: AnySession) -> None:
    assert isinstance(session, Session)
    session.rollback()


async def _sync_write_one(session: AnySession) -> None:
    """A trivial statement that opens a transaction so commit/rollback has effect."""
    assert isinstance(session, Session)
    session.execute(text("SELECT 1"))


@asynccontextmanager
async def _async_session() -> AsyncGenerator[AnySession, None]:
    engine = create_async_engine("sqlite+aiosqlite://")
    session = async_sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


async def _async_commit(session: AnySession) -> None:
    assert isinstance(session, AsyncSession)
    await session.commit()


async def _async_rollback(session: AnySession) -> None:
    assert isinstance(session, AsyncSession)
    await session.rollback()


async def _async_write_one(session: AnySession) -> None:
    assert isinstance(session, AsyncSession)
    await session.execute(text("SELECT 1"))


SYNC = Variant("sync", _sync_session, _sync_commit, _sync_rollback, _sync_write_one)
ASYNC = Variant(
    "async", _async_session, _async_commit, _async_rollback, _async_write_one
)

variant = pytest.mark.parametrize("v", [SYNC, ASYNC], ids=lambda v: v.name)


@variant
async def test_callback_fires_after_successful_commit(v: Variant) -> None:
    fired: list[str] = []

    async with v.session() as session:
        after_commit(session, lambda: fired.append("done"))
        assert fired == []  # registration does not fire inline
        await v.write_one(session)
        await v.commit(session)

    assert fired == ["done"]


@variant
async def test_callback_does_not_fire_on_rollback(v: Variant) -> None:
    fired: list[str] = []

    async with v.session() as session:
        after_commit(session, lambda: fired.append("done"))
        await v.write_one(session)
        await v.rollback(session)

    assert fired == []


@variant
async def test_callback_does_not_fire_when_session_closes_without_commit(
    v: Variant,
) -> None:
    """If the request raises and `get_db` closes the session, no commit happens
    and the listener must not fire (FastAPI's normal exception path)."""
    fired: list[str] = []

    async with v.session() as session:
        after_commit(session, lambda: fired.append("done"))
        await v.write_one(session)
        # session closes via `async with` exit without an explicit commit

    assert fired == []


@variant
async def test_multiple_callbacks_all_fire_in_registration_order(v: Variant) -> None:
    fired: list[str] = []

    async with v.session() as session:
        after_commit(session, lambda: fired.append("first"))
        after_commit(session, lambda: fired.append("second"))
        after_commit(session, lambda: fired.append("third"))
        await v.write_one(session)
        await v.commit(session)

    assert fired == ["first", "second", "third"]


@variant
async def test_callback_fires_once_then_detaches(v: Variant) -> None:
    """`once=True` semantics: a second commit on the same session must not re-fire."""
    fired: list[str] = []

    async with v.session() as session:
        after_commit(session, lambda: fired.append("done"))
        await v.write_one(session)
        await v.commit(session)
        assert fired == ["done"]

        # Second commit on the same session — listener should have detached.
        await v.write_one(session)
        await v.commit(session)

    assert fired == ["done"]


@variant
async def test_callback_exception_is_swallowed_and_logged(
    v: Variant, caplog: pytest.LogCaptureFixture
) -> None:
    """A broken broadcast must not poison SQLAlchemy's event dispatch. Other
    callbacks on the same commit still fire; the failure is logged."""
    fired: list[str] = []

    def explode() -> None:
        raise RuntimeError("broadcast boom")

    async with v.session() as session:
        after_commit(session, explode)
        after_commit(session, lambda: fired.append("after-explode"))
        await v.write_one(session)
        with caplog.at_level(logging.ERROR, logger="shared.websocket.in_tx"):
            await v.commit(session)

    assert fired == ["after-explode"]
    assert any("after_commit callback failed" in rec.message for rec in caplog.records)


@variant
async def test_callback_registered_after_commit_fires_on_next_commit(
    v: Variant,
) -> None:
    """The listener attaches to the session, not a specific transaction. A
    callback registered after one commit binds to the *next* commit."""
    fired: list[str] = []

    async with v.session() as session:
        await v.write_one(session)
        await v.commit(session)
        assert fired == []

        after_commit(session, lambda: fired.append("late"))
        await v.write_one(session)
        await v.commit(session)

    assert fired == ["late"]
