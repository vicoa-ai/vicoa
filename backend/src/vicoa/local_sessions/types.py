"""Shapes shared by every native-session source (Claude, Codex, ...)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

Sender = Literal["user", "agent"]


class LocalSessionError(Exception):
    """A source can't list or read sessions; the message is shown to the user."""


class LocalSessionNotFound(LocalSessionError):
    """No native session with that id on this machine."""


def iso(epoch_seconds: float | None) -> str | None:
    if epoch_seconds is None:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class LocalSession:
    """One session an agent keeps on this machine, as the import list shows it."""

    agent: str
    native_id: str
    title: str
    cwd: str | None
    updated_at: float | None
    created_at: float | None = None
    git_branch: str | None = None
    #: Where the agent says it was started (Claude `entrypoint`, Codex
    #: `originator`), verbatim.
    source: str | None = None
    #: The same, for people: "Terminal", "Claude desktop", "VS Code".
    source_label: str | None = None
    #: Run by a script or an SDK rather than a person (hidden by default).
    scripted: bool = False

    def to_wire(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "native_id": self.native_id,
            "title": self.title,
            "cwd": self.cwd,
            "updated_at": iso(self.updated_at),
            "created_at": iso(self.created_at),
            "git_branch": self.git_branch,
            "source": self.source,
            "source_label": self.source_label,
            "scripted": self.scripted,
        }


@dataclass(frozen=True)
class HistoryMessage:
    """One row of an imported transcript, already rendered like a live one."""

    sender: Sender
    content: str
    created_at: float
    metadata: dict[str, Any] | None = None

    def to_wire(self) -> dict[str, Any]:
        wire: dict[str, Any] = {
            "sender": self.sender,
            "content": self.content,
            "created_at": iso(self.created_at),
        }
        if self.metadata:
            wire["message_metadata"] = self.metadata
        return wire


@dataclass(frozen=True)
class Transcript:
    session: LocalSession
    messages: list[HistoryMessage]
