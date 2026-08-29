"""Unit tests for the machine_agent_models write-on-change cache logic.

Exercises ``upsert_machine_agent_models`` against a mock session so the
decision logic (insert / skip-unchanged / update / skip-empty / normalize) is
covered without a database.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from shared.database import MachineAgentModels
from servers.shared.db.queries import (
    _agent_models_hash,
    _normalize_agent_models,
    upsert_machine_agent_models,
)

_MODELS = [
    {"id": "opencode/big-pickle", "label": "Big Pickle"},
    {"id": "opencode/deepseek", "label": "DeepSeek"},
]
_MID = uuid4()
_UID = uuid4()
_AGENT = "opencode"


def _call(db: MagicMock, models: object) -> bool:
    return upsert_machine_agent_models(
        db, machine_id=_MID, agent_type=_AGENT, user_id=_UID, models=models
    )


def test_inserts_when_absent() -> None:
    db = MagicMock()
    db.get.return_value = None
    assert _call(db, _MODELS) is True
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert isinstance(added, MachineAgentModels)
    assert added.machine_id == _MID
    assert added.agent_type == _AGENT
    assert added.user_id == _UID
    assert added.models == _normalize_agent_models(_MODELS)


def test_skips_when_unchanged() -> None:
    """The common case: same list across sessions -> no write."""
    db = MagicMock()
    existing = MagicMock()
    existing.models_hash = _agent_models_hash(_normalize_agent_models(_MODELS))
    db.get.return_value = existing
    assert _call(db, _MODELS) is False
    db.add.assert_not_called()


def test_updates_when_changed() -> None:
    db = MagicMock()
    existing = MagicMock()
    existing.models_hash = "stale-hash"
    db.get.return_value = existing
    assert _call(db, _MODELS) is True
    db.add.assert_not_called()  # in-place update, not insert
    assert existing.models == _normalize_agent_models(_MODELS)
    assert existing.models_hash == _agent_models_hash(_normalize_agent_models(_MODELS))


def test_skips_empty_never_clobbers() -> None:
    """An empty/missing list must not overwrite a known-good cached list."""
    db = MagicMock()
    assert _call(db, []) is False
    assert _call(db, None) is False
    db.get.assert_not_called()
    db.add.assert_not_called()


def test_normalizes_and_drops_junk() -> None:
    db = MagicMock()
    db.get.return_value = None
    messy = [
        {"id": "a", "label": "A"},
        {"label": "no id"},  # dropped (no id)
        "junk",  # dropped (not a dict)
        {"id": "b"},  # label defaults to id
    ]
    _call(db, messy)
    added = db.add.call_args.args[0]
    assert added.models == [{"id": "a", "label": "A"}, {"id": "b", "label": "b"}]
