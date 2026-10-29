"""A NUL in a synced command must not fail the whole ``/commands/sync``.

Postgres jsonb rejects ``\\u0000``. A ZIP saved as SKILL.md gives older CLIs a
description starting ``PK\\x03\\x04\\x14\\x00``, and the sync then 500s every
time, so none of that agent's commands are stored. The engine's
``json_serializer`` (`json_dumps_without_nul`) is the storage boundary that
strips it, for every JSON/JSONB column and every client version.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.database.models import SlashCommands, User
from shared.database.session import engine, get_db
from shared.database.utils import json_dumps_without_nul
from servers.api.auth import get_current_user_id
from servers.api.routers import agent_router


@pytest.fixture
def client(test_db):
    user = test_db.query(User).first()
    app = FastAPI()
    app.include_router(agent_router, prefix="/api/v1")

    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_id] = lambda: str(user.id)
    return TestClient(app)


def test_sync_with_nul_in_a_description_stores_the_rest(test_db, client):
    resp = client.post(
        "/api/v1/commands/sync",
        json={
            "agent_type": "claude",
            "commands": {
                "broken-thing": {
                    "description": "PK\x03\x04\x14\x00rest",
                    "kind": "skill",
                },
                "ship": {"description": "Ship it", "kind": "command"},
            },
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["synced_count"] == 2
    row = test_db.query(SlashCommands).filter_by(agent_type="claude").one()
    assert row.commands["broken-thing"]["description"] == "PK\x03\x04\x14rest"
    assert row.commands["ship"] == {"description": "Ship it", "kind": "command"}


def test_app_engine_uses_the_serializer():
    # The test engine in conftest sets it as well, so the endpoint test above
    # can't tell if the app engine loses it.
    # Set by the JSON-capable dialects; not declared on the base `Dialect`.
    serializer = getattr(engine.dialect, "_json_serializer", None)
    assert serializer is json_dumps_without_nul


def test_serializer_strips_nul_from_nested_strings_and_keys():
    value = {"a\x00": ["x\x00y", {"k": "\x00"}], "n": 1, "none": None}

    assert json.loads(json_dumps_without_nul(value)) == {
        "a": ["xy", {"k": ""}],
        "n": 1,
        "none": None,
    }


def test_serializer_is_plain_json_dumps_without_nul():
    value = {"description": "Ship it", "files": ["a.py", "b/c.md"], "n": 1.5}

    assert json_dumps_without_nul(value) == json.dumps(value)


def test_serializer_keeps_a_literal_backslash_u0000():
    # Six characters, not a NUL: the text "\u0000" in a description.
    value = {"description": "write \\u0000 to end it", "real": "\x00"}

    assert json.loads(json_dumps_without_nul(value)) == {
        "description": "write \\u0000 to end it",
        "real": "",
    }
