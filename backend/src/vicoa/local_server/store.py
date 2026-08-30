"""SQLite persistence for local-only (logged-out) desktop sessions.

Mirrors the slice of the backend schema the web renderer and the headless
SDK actually touch: ``agent_instances`` and ``messages``, with the same
pending-delivery semantics as the cloud (``last_read_message_id`` advances
when messages are returned to the agent — the local equivalent of a
``delivered_to_agent`` flag).

Ids are UUID strings; timestamps are stored wire-ready as
``YYYY-MM-DDTHH:MM:SS.ffffffZ`` (fixed-width, so lexicographic order equals
chronological order). A monotonic per-message ``seq`` breaks same-microsecond
ties deterministically.

Thread-safe: one connection guarded by an RLock; every public method commits
before returning. WS-broadcast listeners are invoked after commit, outside
the lock.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .envelopes import (
    build_instance_created_update,
    build_instance_update,
    build_new_message_update,
)

logger = logging.getLogger(__name__)

DEFAULT_STORE_PATH = Path.home() / ".vicoa" / "local_store.db"

# Mirrors shared.database.enums.AgentStatus (not importable from the packaged
# CLI); parity is asserted in tests/test_local_envelopes.py.
AGENT_STATUS_VALUES: frozenset[str] = frozenset(
    {
        "STARTING",
        "ACTIVE",
        "AWAITING_INPUT",
        "PAUSED",
        "STALE",
        "COMPLETED",
        "REVIEWED",
        "FAILED",
        "KILLED",
        "DISCONNECTED",
        "DELETED",
    }
)

# Mirrors servers.shared.db.queries WS_FETCH_* (same reason as above).
WS_FETCH_PAGE_LIMIT = 200
WS_FETCH_SAFETY_WINDOW = timedelta(seconds=30)

_RECENT_DIRECTORIES_LIMIT = 10

# Namespace for deterministic per-agent-type "user_agent" ids, so the same
# agent type always maps to the same agent_type_id across restarts.
_USER_AGENT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "vicoa-local-user-agent")


class InstanceConflictError(Exception):
    """Raised when registering an instance id that already exists."""


class InstanceNotFoundError(Exception):
    """Raised when an operation targets a missing (or deleted) instance."""


def utc_now_iso() -> str:
    """Current UTC time in the fixed wire format (naive isoformat + Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _parse_wire_timestamp(value: str) -> datetime:
    """Parse a wire timestamp (``...Z`` or offset-aware ISO) to aware UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_wire_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _dump_json(value: dict | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"))


def _load_json(value: str | None) -> dict | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


@dataclass(slots=True)
class StoredInstance:
    """One agent_instances row, timestamps already wire-formatted."""

    id: str
    user_agent_id: str
    agent_type_name: str
    status: str
    name: str | None
    project: str | None
    home_dir: str | None
    machine_id: str | None
    started_at: str
    ended_at: str | None
    last_heartbeat_at: str | None
    last_read_message_id: str | None
    instance_metadata: dict | None
    session_config: dict | None
    git_diff: str | None
    updated_at: str
    pinned_at: str | None


@dataclass(slots=True)
class StoredMessage:
    """One messages row, ``created_at`` already wire-formatted."""

    id: str
    agent_instance_id: str
    sender_type: str
    content: str
    requires_user_input: bool
    message_metadata: dict | None
    created_at: str
    sender_user_id: str | None
    seq: int


class LocalStore:
    """Thread-safe SQLite store with an in-process broadcast hook."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        path = Path(db_path) if db_path is not None else DEFAULT_STORE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        self._listeners: list[Callable[[dict], None]] = []

    # ------------------------------------------------------------------
    # Setup / events
    # ------------------------------------------------------------------
    def _create_tables(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_instances (
                    id TEXT PRIMARY KEY,
                    user_agent_id TEXT NOT NULL,
                    agent_type_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    name TEXT,
                    project TEXT,
                    home_dir TEXT,
                    machine_id TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    last_heartbeat_at TEXT,
                    last_read_message_id TEXT,
                    instance_metadata TEXT,
                    session_config TEXT,
                    git_diff TEXT,
                    updated_at TEXT NOT NULL,
                    pinned_at TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    agent_instance_id TEXT NOT NULL,
                    sender_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    requires_user_input INTEGER NOT NULL DEFAULT 0,
                    message_metadata TEXT,
                    created_at TEXT NOT NULL,
                    sender_user_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_messages_instance_order
                    ON messages (agent_instance_id, created_at, seq);
                CREATE TABLE IF NOT EXISTS recent_directories (
                    directory TEXT PRIMARY KEY,
                    used_at TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def add_listener(self, callback: Callable[[dict], None]) -> None:
        """Subscribe to post-commit ``update`` payloads (envelope-shaped)."""
        self._listeners.append(callback)

    def _emit(self, payloads: Iterable[dict]) -> None:
        for payload in payloads:
            for listener in list(self._listeners):
                try:
                    listener(payload)
                except Exception:
                    logger.exception("local store: update listener raised")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # Row mapping
    # ------------------------------------------------------------------
    @staticmethod
    def _instance_from_row(row: sqlite3.Row) -> StoredInstance:
        return StoredInstance(
            id=row["id"],
            user_agent_id=row["user_agent_id"],
            agent_type_name=row["agent_type_name"],
            status=row["status"],
            name=row["name"],
            project=row["project"],
            home_dir=row["home_dir"],
            machine_id=row["machine_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            last_heartbeat_at=row["last_heartbeat_at"],
            last_read_message_id=row["last_read_message_id"],
            instance_metadata=_load_json(row["instance_metadata"]),
            session_config=_load_json(row["session_config"]),
            git_diff=row["git_diff"],
            updated_at=row["updated_at"],
            pinned_at=row["pinned_at"],
        )

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> StoredMessage:
        return StoredMessage(
            id=row["id"],
            agent_instance_id=row["agent_instance_id"],
            sender_type=row["sender_type"],
            content=row["content"],
            requires_user_input=bool(row["requires_user_input"]),
            message_metadata=_load_json(row["message_metadata"]),
            created_at=row["created_at"],
            sender_user_id=row["sender_user_id"],
            seq=row["seq"],
        )

    def _get_instance_row(self, instance_id: str) -> sqlite3.Row | None:
        cursor = self._conn.execute(
            "SELECT * FROM agent_instances WHERE id = ?", (instance_id,)
        )
        return cursor.fetchone()

    def _get_message_row(self, message_id: str) -> sqlite3.Row | None:
        cursor = self._conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        )
        return cursor.fetchone()

    def _touch_instance(self, instance_id: str, fields: dict[str, Any]) -> None:
        fields = dict(fields)
        fields["updated_at"] = utc_now_iso()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        self._conn.execute(
            f"UPDATE agent_instances SET {assignments} WHERE id = ?",
            (*fields.values(), instance_id),
        )

    # ------------------------------------------------------------------
    # Instances
    # ------------------------------------------------------------------
    @staticmethod
    def user_agent_id_for(agent_type: str) -> str:
        return str(uuid.uuid5(_USER_AGENT_NAMESPACE, agent_type.strip().lower()))

    def register_instance(
        self,
        *,
        agent_type: str,
        agent_instance_id: str | None = None,
        name: str | None = None,
        project: str | None = None,
        home_dir: str | None = None,
        transport: str | None = None,
        source: str | None = None,
        machine_id: str | None = None,
        session_config: dict | None = None,
        worktree_name: str | None = None,
        status: str = "ACTIVE",
    ) -> StoredInstance:
        """Create an instance row (mirrors ``POST /api/v1/agent-instances``).

        Raises :class:`InstanceConflictError` when the id already exists —
        the SDK handles the resulting 409 by fetching the existing row.
        """
        instance_id = agent_instance_id or str(uuid.uuid4())
        now = utc_now_iso()
        metadata: dict[str, Any] = {}
        if transport:
            metadata["transport"] = transport
        if source:
            metadata["source"] = source
        if worktree_name:
            metadata["worktree_name"] = worktree_name
        with self._lock:
            if self._get_instance_row(instance_id) is not None:
                raise InstanceConflictError(instance_id)
            self._conn.execute(
                """
                INSERT INTO agent_instances (
                    id, user_agent_id, agent_type_name, status, name, project,
                    home_dir, machine_id, started_at, ended_at,
                    last_heartbeat_at, last_read_message_id, instance_metadata,
                    session_config, git_diff, updated_at, pinned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?, ?, NULL, ?, NULL)
                """,
                (
                    instance_id,
                    self.user_agent_id_for(agent_type),
                    agent_type,
                    status,
                    name,
                    project,
                    home_dir,
                    machine_id,
                    now,
                    now,
                    _dump_json(metadata or None),
                    _dump_json(session_config),
                    now,
                ),
            )
            self._conn.commit()
            row = self._get_instance_row(instance_id)
        assert row is not None
        instance = self._instance_from_row(row)
        self._emit([build_instance_created_update(instance)])
        return instance

    def get_instance(self, instance_id: str) -> StoredInstance | None:
        with self._lock:
            row = self._get_instance_row(instance_id)
        return self._instance_from_row(row) if row is not None else None

    def list_instances(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[tuple[StoredInstance, StoredMessage | None, int]], int]:
        """Instances (newest activity first) with latest message + count.

        Returns ``([(instance, latest_message, chat_length), ...], total)``
        for the paginated REST list endpoint.
        """
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM agent_instances WHERE status != 'DELETED'"
            ).fetchone()[0]
            rows = self._conn.execute(
                """
                SELECT * FROM agent_instances WHERE status != 'DELETED'
                ORDER BY updated_at DESC, started_at DESC LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
            result: list[tuple[StoredInstance, StoredMessage | None, int]] = []
            for row in rows:
                instance = self._instance_from_row(row)
                latest_row = self._conn.execute(
                    """
                    SELECT * FROM messages WHERE agent_instance_id = ?
                    ORDER BY created_at DESC, seq DESC LIMIT 1
                    """,
                    (instance.id,),
                ).fetchone()
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE agent_instance_id = ?",
                    (instance.id,),
                ).fetchone()[0]
                latest = (
                    self._message_from_row(latest_row)
                    if latest_row is not None
                    else None
                )
                result.append((instance, latest, count))
        return result, total

    def get_instance_messages(
        self,
        instance_id: str,
        *,
        message_limit: int | None = None,
        before_message_id: str | None = None,
    ) -> list[StoredMessage]:
        """Chronological message page (mirrors the backend detail endpoint:
        DESC + LIMIT, then reversed)."""
        with self._lock:
            params: list[Any] = [instance_id]
            where = "agent_instance_id = ?"
            if before_message_id:
                cursor_row = self._get_message_row(before_message_id)
                if cursor_row is not None:
                    where += " AND (created_at < ? OR (created_at = ? AND seq < ?))"
                    params.extend(
                        (
                            cursor_row["created_at"],
                            cursor_row["created_at"],
                            cursor_row["seq"],
                        )
                    )
            sql = (
                f"SELECT * FROM messages WHERE {where} "
                "ORDER BY created_at DESC, seq DESC"
            )
            if message_limit is not None:
                sql += " LIMIT ?"
                params.append(message_limit)
            rows = self._conn.execute(sql, params).fetchall()
        return [self._message_from_row(row) for row in reversed(rows)]

    def update_instance_status(self, instance_id: str, status: str) -> StoredInstance:
        """Mirror ``PUT /api/v1/agent-instances/{id}/status`` semantics."""
        if status not in AGENT_STATUS_VALUES:
            raise ValueError(f"Invalid status value: {status}")
        with self._lock:
            row = self._get_instance_row(instance_id)
            if row is None or row["status"] == "DELETED":
                raise InstanceNotFoundError(instance_id)
            fields: dict[str, Any] = {"status": status}
            if status == "COMPLETED":
                fields["ended_at"] = utc_now_iso()
            self._touch_instance(instance_id, fields)
            self._conn.commit()
            updated = self._get_instance_row(instance_id)
        assert updated is not None
        instance = self._instance_from_row(updated)
        self._emit([build_instance_update(instance)])
        return instance

    def end_session(self, instance_id: str) -> StoredInstance:
        """Mirror ``POST /api/v1/sessions/end`` (mark COMPLETED)."""
        return self.update_instance_status(instance_id, "COMPLETED")

    def patch_instance(
        self,
        instance_id: str,
        *,
        name: str | None = None,
        session_config_merge: dict | None = None,
    ) -> StoredInstance:
        """Mirror ``PATCH /api/v1/agent-instances/{id}`` (name + config merge)."""
        with self._lock:
            row = self._get_instance_row(instance_id)
            if row is None or row["status"] == "DELETED":
                raise InstanceNotFoundError(instance_id)
            fields: dict[str, Any] = {}
            if name is not None:
                fields["name"] = name
            if session_config_merge is not None:
                merged = _load_json(row["session_config"]) or {}
                merged.update(session_config_merge)
                fields["session_config"] = _dump_json(merged)
            if fields:
                self._touch_instance(instance_id, fields)
                self._conn.commit()
            updated = self._get_instance_row(instance_id)
        assert updated is not None
        instance = self._instance_from_row(updated)
        if fields:
            self._emit([build_instance_update(instance)])
        return instance

    def delete_instance(self, instance_id: str) -> StoredInstance:
        """Soft-delete an instance (mirrors backend ``delete_agent_instance``).

        Deletes the instance's messages to reclaim space and marks the row
        ``DELETED`` — the store filters ``DELETED`` rows out of
        :meth:`list_instances`, and the detail endpoint 404s on them, so the
        session disappears from the renderer exactly as on the cloud. Raises
        :class:`InstanceNotFoundError` for an unknown id (→ 404). Re-deleting an
        already-``DELETED`` row is idempotent (returns 200), matching the cloud
        query, which finds the soft-deleted row by id regardless of status.

        A soft delete (over a hard row removal) is deliberate: an orphaned
        headless child that later posts via ``add_agent_message`` finds the
        ``DELETED`` row and keeps its status (it is not resurrected into the
        sidebar), whereas a missing row would be auto-recreated.
        """
        with self._lock:
            row = self._get_instance_row(instance_id)
            if row is None:
                raise InstanceNotFoundError(instance_id)
            self._conn.execute(
                "DELETE FROM messages WHERE agent_instance_id = ?", (instance_id,)
            )
            self._touch_instance(instance_id, {"status": "DELETED"})
            self._conn.commit()
            updated = self._get_instance_row(instance_id)
        assert updated is not None
        instance = self._instance_from_row(updated)
        # Broadcast the terminal status so connected renderers drop the row
        # live (cloud parity: delete bridges an instance-update, DELETED body).
        self._emit([build_instance_update(instance)])
        return instance

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    def _insert_message(
        self,
        *,
        instance_id: str,
        sender_type: str,
        content: str,
        requires_user_input: bool,
        message_metadata: dict | None,
        sender_user_id: str | None,
    ) -> StoredMessage:
        message_id = str(uuid.uuid4())
        created_at = utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO messages (
                id, agent_instance_id, sender_type, content,
                requires_user_input, message_metadata, created_at,
                sender_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                instance_id,
                sender_type,
                content,
                1 if requires_user_input else 0,
                _dump_json(message_metadata),
                created_at,
                sender_user_id,
            ),
        )
        row = self._get_message_row(message_id)
        assert row is not None
        return self._message_from_row(row)

    def _queued_user_messages_locked(
        self, instance_row: sqlite3.Row, advance_last_read: bool
    ) -> list[StoredMessage]:
        """USER messages after the instance's last-read cursor (cloud
        ``get_queued_user_messages`` semantics; stale check is the caller's)."""
        last_read_id = instance_row["last_read_message_id"]
        params: list[Any] = [instance_row["id"]]
        where = "agent_instance_id = ? AND sender_type = 'USER'"
        if last_read_id:
            last_read_row = self._get_message_row(last_read_id)
            if last_read_row is None:
                return []
            where += " AND (created_at > ? OR (created_at = ? AND seq > ?))"
            params.extend(
                (
                    last_read_row["created_at"],
                    last_read_row["created_at"],
                    last_read_row["seq"],
                )
            )
        rows = self._conn.execute(
            f"SELECT * FROM messages WHERE {where} ORDER BY created_at, seq",
            params,
        ).fetchall()
        messages = [self._message_from_row(row) for row in rows]
        if messages and advance_last_read:
            self._conn.execute(
                "UPDATE agent_instances SET last_read_message_id = ? WHERE id = ?",
                (messages[-1].id, instance_row["id"]),
            )
        return messages

    def add_agent_message(
        self,
        *,
        agent_instance_id: str,
        content: str,
        agent_type: str | None = None,
        requires_user_input: bool = False,
        message_metadata: dict | None = None,
        git_diff: str | None = None,
    ) -> tuple[StoredMessage, StoredInstance, list[StoredMessage]]:
        """Mirror ``POST /api/v1/messages/agent``.

        Creates the instance when unknown (requires ``agent_type`` then),
        returns queued USER messages since the agent's last read, advances the
        read cursor to the new agent message, and updates instance status
        (AWAITING_INPUT for questions, ACTIVE otherwise) + heartbeat.
        """
        emit: list[dict] = []
        with self._lock:
            row = self._get_instance_row(agent_instance_id)
            if row is None:
                if not agent_type:
                    raise ValueError(
                        "agent_type is required when agent instance does not exist"
                    )
                now = utc_now_iso()
                self._conn.execute(
                    """
                    INSERT INTO agent_instances (
                        id, user_agent_id, agent_type_name, status, name,
                        project, home_dir, machine_id, started_at, ended_at,
                        last_heartbeat_at, last_read_message_id,
                        instance_metadata, session_config, git_diff,
                        updated_at, pinned_at
                    ) VALUES (?, ?, ?, 'ACTIVE', NULL, NULL, NULL, NULL, ?,
                              NULL, ?, NULL, NULL, NULL, NULL, ?, NULL)
                    """,
                    (
                        agent_instance_id,
                        self.user_agent_id_for(agent_type),
                        agent_type,
                        now,
                        now,
                        now,
                    ),
                )
                row = self._get_instance_row(agent_instance_id)
                assert row is not None
                emit.append(build_instance_created_update(self._instance_from_row(row)))

            queued = self._queued_user_messages_locked(row, advance_last_read=True)

            message = self._insert_message(
                instance_id=agent_instance_id,
                sender_type="AGENT",
                content=content,
                requires_user_input=requires_user_input,
                message_metadata=message_metadata,
                sender_user_id=None,
            )

            fields: dict[str, Any] = {
                "last_read_message_id": message.id,
                "last_heartbeat_at": utc_now_iso(),
            }
            if row["status"] not in ("COMPLETED", "DELETED"):
                fields["status"] = "AWAITING_INPUT" if requires_user_input else "ACTIVE"
            if git_diff is not None:
                fields["git_diff"] = git_diff
            self._touch_instance(agent_instance_id, fields)
            self._conn.commit()
            updated_row = self._get_instance_row(agent_instance_id)
        assert updated_row is not None
        instance = self._instance_from_row(updated_row)
        emit.append(build_new_message_update(message))
        emit.append(build_instance_update(instance))
        self._emit(emit)
        return message, instance, queued

    def add_user_message(
        self,
        *,
        agent_instance_id: str,
        content: str,
        mark_as_read: bool,
        message_metadata: dict | None = None,
        sender_user_id: str | None = None,
    ) -> StoredMessage:
        """Mirror the user-message writes.

        ``mark_as_read=False`` (the renderer's POST) leaves the message
        pending for the agent's next ``/messages/pending`` poll / WS catch-up;
        ``mark_as_read=True`` (``POST /api/v1/messages/user``) advances the
        read cursor immediately. Reactivates non-deleted instances (ACTIVE).
        """
        with self._lock:
            row = self._get_instance_row(agent_instance_id)
            if row is None:
                raise InstanceNotFoundError(agent_instance_id)
            message = self._insert_message(
                instance_id=agent_instance_id,
                sender_type="USER",
                content=content,
                requires_user_input=False,
                message_metadata=message_metadata,
                sender_user_id=sender_user_id,
            )
            fields: dict[str, Any] = {}
            if row["status"] != "DELETED":
                fields["status"] = "ACTIVE"
            if mark_as_read:
                fields["last_read_message_id"] = message.id
            if fields:
                self._touch_instance(agent_instance_id, fields)
            self._conn.commit()
        self._emit([build_new_message_update(message)])
        return message

    def pending_messages(
        self, agent_instance_id: str, last_read_message_id: str | None
    ) -> tuple[list[StoredMessage], str]:
        """Mirror ``GET /api/v1/messages/pending``: ``(messages, ok|stale)``.

        Returning messages advances ``last_read_message_id`` — the pending
        bookkeeping that stops the next poll re-delivering the same rows.
        """
        with self._lock:
            row = self._get_instance_row(agent_instance_id)
            if row is None:
                raise InstanceNotFoundError(agent_instance_id)
            if (
                last_read_message_id is not None
                and row["last_read_message_id"] != last_read_message_id
            ):
                return [], "stale"
            messages = self._queued_user_messages_locked(row, advance_last_read=True)
            self._conn.commit()
        return messages, "ok"

    def mark_message_requires_input(
        self, message_id: str
    ) -> tuple[str, list[StoredMessage], str]:
        """Mirror ``PATCH /api/v1/messages/{id}/request-input``.

        Returns ``(agent_instance_id, queued_user_messages, ok|stale)``. When
        nothing is queued the instance flips to AWAITING_INPUT (broadcast).
        """
        emit: list[dict] = []
        with self._lock:
            message_row = self._get_message_row(message_id)
            if message_row is None or message_row["sender_type"] != "AGENT":
                raise InstanceNotFoundError(message_id)
            if bool(message_row["requires_user_input"]):
                raise ValueError("Message already requires user input")
            instance_row = self._get_instance_row(message_row["agent_instance_id"])
            if instance_row is None:
                raise InstanceNotFoundError(message_row["agent_instance_id"])

            self._conn.execute(
                "UPDATE messages SET requires_user_input = 1 WHERE id = ?",
                (message_id,),
            )

            # Cloud parity: the queued lookup treats the marked message as the
            # last-read cursor and reports "stale" when the instance has
            # already moved past it.
            if instance_row["last_read_message_id"] != message_id:
                self._conn.commit()
                return message_row["agent_instance_id"], [], "stale"

            queued = self._queued_user_messages_locked(
                instance_row, advance_last_read=True
            )
            if not queued:
                self._touch_instance(instance_row["id"], {"status": "AWAITING_INPUT"})
            self._conn.commit()
            updated_row = self._get_instance_row(instance_row["id"])
        assert updated_row is not None
        if not queued:
            emit.append(build_instance_update(self._instance_from_row(updated_row)))
        self._emit(emit)
        return updated_row["id"], queued, "ok"

    # ------------------------------------------------------------------
    # WS catch-up fetches (mirror servers.shared.db.queries)
    # ------------------------------------------------------------------
    def fetch_messages(
        self,
        instance_id: str,
        after: dict | None,
        *,
        include_agent_messages: bool,
        page_limit: int = WS_FETCH_PAGE_LIMIT,
    ) -> tuple[list[dict], bool, str | None]:
        """Mirror ``fetch_session_messages``: ``(rows, has_more, resync)``.

        Rows are ``new-message`` envelope bodies. Session-scoped callers
        (``include_agent_messages=False``) with no watermark fall back to the
        instance's ``last_read_message_id`` cursor so a reconnecting wrapper
        doesn't replay already-processed user messages.
        """
        with self._lock:
            params: list[Any] = [instance_id]
            where = "agent_instance_id = ?"
            if not include_agent_messages:
                where += " AND sender_type = 'USER'"

            if not after or after.get("created_at") is None:
                if not include_agent_messages:
                    instance_row = self._get_instance_row(instance_id)
                    last_read_id = (
                        instance_row["last_read_message_id"]
                        if instance_row is not None
                        else None
                    )
                    if last_read_id:
                        last_read_row = self._get_message_row(last_read_id)
                        if last_read_row is not None:
                            where += " AND created_at > ?"
                            params.append(last_read_row["created_at"])
            elif after.get("id") is None:
                watermark = _parse_wire_timestamp(str(after["created_at"]))
                floor = _to_wire_timestamp(watermark - WS_FETCH_SAFETY_WINDOW)
                where += " AND created_at >= ?"
                params.append(floor)
            else:
                cursor_row = self._get_message_row(str(after["id"]))
                if cursor_row is None or cursor_row["agent_instance_id"] != instance_id:
                    return [], False, "missing_history"
                where += " AND (created_at > ? OR (created_at = ? AND seq > ?))"
                params.extend(
                    (
                        cursor_row["created_at"],
                        cursor_row["created_at"],
                        cursor_row["seq"],
                    )
                )

            rows = self._conn.execute(
                f"SELECT * FROM messages WHERE {where} "
                "ORDER BY created_at, seq LIMIT ?",
                (*params, page_limit + 1),
            ).fetchall()

        has_more = len(rows) > page_limit
        bodies = [
            build_new_message_update(self._message_from_row(row))["body"]
            for row in rows[:page_limit]
        ]
        return bodies, has_more, None

    def fetch_instances(self, updated_after: str | None) -> list[dict]:
        """Mirror ``fetch_user_instances``: instance-update envelope bodies."""
        with self._lock:
            params: list[Any] = []
            where = "1 = 1"
            if updated_after is not None:
                floor = _to_wire_timestamp(
                    _parse_wire_timestamp(updated_after) - WS_FETCH_SAFETY_WINDOW
                )
                where = "updated_at >= ?"
                params.append(floor)
            rows = self._conn.execute(
                f"SELECT * FROM agent_instances WHERE {where} ORDER BY updated_at",
                params,
            ).fetchall()
        return [
            build_instance_update(self._instance_from_row(row))["body"] for row in rows
        ]

    # ------------------------------------------------------------------
    # Recent directories (new-session picker parity)
    # ------------------------------------------------------------------
    def push_recent_directory(self, directory: str) -> None:
        cleaned = directory.strip()
        if not cleaned:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO recent_directories (directory, used_at) VALUES (?, ?) "
                "ON CONFLICT(directory) DO UPDATE SET used_at = excluded.used_at",
                (cleaned, utc_now_iso()),
            )
            self._conn.execute(
                """
                DELETE FROM recent_directories WHERE directory NOT IN (
                    SELECT directory FROM recent_directories
                    ORDER BY used_at DESC LIMIT ?
                )
                """,
                (_RECENT_DIRECTORIES_LIMIT,),
            )
            self._conn.commit()

    def recent_directories(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT directory FROM recent_directories ORDER BY used_at DESC"
            ).fetchall()
        return [row["directory"] for row in rows]


__all__ = [
    "AGENT_STATUS_VALUES",
    "InstanceConflictError",
    "InstanceNotFoundError",
    "LocalStore",
    "StoredInstance",
    "StoredMessage",
    "utc_now_iso",
    "WS_FETCH_PAGE_LIMIT",
    "WS_FETCH_SAFETY_WINDOW",
]
