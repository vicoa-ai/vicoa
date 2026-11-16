"""What a task dispatch tells the agent (plans/todos/task-assignment-agents.md).

The message is a pointer plus the rules of the turn, never the comment text:
the agent reads the task and its thread itself, as they stand when its turn
comes, so two triggers merged into one dispatch, an edited comment or a deleted
one all come out right without special handling.

Two modes:

* **Ownership** — the task was assigned to the agent: it owns the status and
  hands the task to a person (`--assignee me`) when it needs one.
* **Reply** — a person's comment is for it: answer in that thread, and leave
  assignee and status alone unless the task is its own and it did real work.

Commands are the `vicoa task` CLI every Vicoa session already has; prose goes
through a quoted heredoc, the one quoting that survives every shell.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

CONTINUITY_NOTE = (
    "Your earlier session on this task could not be resumed, so you start fresh "
    "here. The task and its comment thread are the whole record: read them before "
    "doing anything."
)


@dataclass(frozen=True)
class SinceHandover:
    """What happened to a task while it was out of this agent's hands."""

    # When the agent last handed the task over, in UTC ISO 8601.
    at: str
    # Thread roots with a person's comment since then.
    threads: Sequence[UUID] = ()
    # Plain words for other edits since then: "description edited", "status
    # changed to blocked" — one line each.
    edits: Sequence[str] = ()


@dataclass(frozen=True)
class EarlierSession:
    """Earlier work on the task in a session this one doesn't continue."""

    session_id: UUID
    agent_name: str | None = None
    # The worktree this session starts in is that session's.
    same_folder: bool = False


def _comment_cmd(ref: str, reply_to: UUID | None = None) -> str:
    flag = f" --reply-to {reply_to}" if reply_to is not None else ""
    return f"`vicoa task comment {ref}{flag} - <<'EOF'` … `EOF`"


def _threads_line(ref: str, threads: Sequence[UUID]) -> str:
    if not threads:
        return ""
    listed = ", ".join(f"`{t}`" for t in threads)
    return (
        f"- New comments for you are waiting in thread(s) {listed}. Answer each in "
        f"its own thread: {_comment_cmd(ref, threads[0])} (one reply per thread)."
    )


def _since_lines(ref: str, since: SinceHandover) -> list[str]:
    lines = [
        "",
        f"You had this task before and handed it over at {since.at}. Since then:",
    ]
    if since.threads:
        listed = ", ".join(f"`{t}`" for t in since.threads)
        lines.append(f"- people commented in thread(s) {listed};")
    lines += [f"- {edit};" for edit in since.edits]
    if not since.threads and not since.edits:
        lines.append("- nothing was written on the task; the hand-back is the signal.")
    lines.append(
        "- the code may have moved too: bring your branch up to date with the default "
        "branch before you continue, and say so in your first comment if that changed "
        "the plan."
    )
    return lines


def _earlier_lines(earlier: EarlierSession) -> list[str]:
    who = f" by {earlier.agent_name}" if earlier.agent_name else ""
    where = (
        " You are in the same folder, so its changes are already here."
        if earlier.same_folder
        else ""
    )
    return [
        "",
        f"Earlier work on this task happened in session {earlier.session_id}{who}."
        f"{where} Read it if you need its reasoning: `vicoa session get "
        f"{earlier.session_id} --all`.",
    ]


def ownership_prompt(
    *,
    ref: str,
    title: str,
    agent_name: str,
    assigned_by: str | None,
    threads: Sequence[UUID] = (),
    since: SinceHandover | None = None,
    earlier: EarlierSession | None = None,
    continuity: bool = False,
) -> str:
    by = f" by {assigned_by}" if assigned_by else ""
    again = " again" if since is not None else ""
    lines = [
        f'Task {ref} "{title}" was assigned to you ({agent_name}){again}{by}. '
        "You own it until you hand it back.",
        "",
        f"- Read it and its whole thread first: `vicoa task get {ref}` and "
        f"`vicoa task comments {ref}`.",
        f"- When you start: `vicoa task update {ref} --status in_progress`.",
        f"- Report progress and results as top-level comments: {_comment_cmd(ref)}.",
        f"- Delivered (a PR link or the evidence in a comment): "
        f"`vicoa task update {ref} --status in_review`.",
        "- Need a person (a decision, an answer, access)? Ask in one top-level "
        "comment, options first with your recommendation, then hand it over: "
        f"`vicoa task update {ref} --assignee me`. Their reply comes back to you "
        "here.",
    ]
    if since is None:
        threads_line = _threads_line(ref, threads)
        if threads_line:
            lines.append(threads_line)
    else:
        lines += _since_lines(ref, since)
    if earlier is not None:
        lines += _earlier_lines(earlier)
    if continuity:
        lines += ["", CONTINUITY_NOTE]
    return "\n".join(lines)


def reply_prompt(
    *,
    ref: str,
    title: str,
    agent_name: str,
    threads: Sequence[UUID],
    assigned_to_you: bool,
    earlier: EarlierSession | None = None,
    continuity: bool = False,
) -> str:
    first = threads[0] if threads else None
    where = (
        f"thread `{first}`"
        if len(threads) == 1
        else "threads " + ", ".join(f"`{t}`" for t in threads)
        if threads
        else "its comments"
    )
    lines = [
        f'Someone commented on task {ref} "{title}" for you ({agent_name}), in {where}.',
        "",
        f"- Read the task and its thread: `vicoa task comments {ref}`.",
        "- Do what they ask, then reply in that thread: "
        f"{_comment_cmd(ref, first)}. One reply per thread.",
    ]
    if assigned_to_you:
        lines.append(
            "- The task is assigned to you: if this turn does real work on it, keep "
            f"its status current (`vicoa task update {ref} --status …`). A purely "
            "conversational turn leaves it alone."
        )
    else:
        lines.append(
            "- Leave the assignee and the status alone. If they answered a question "
            "you asked when you handed the task to them, take it back first and "
            f"carry on: `vicoa task update {ref} --assignee self`."
        )
    if earlier is not None:
        lines += _earlier_lines(earlier)
    if continuity:
        lines += ["", CONTINUITY_NOTE]
    return "\n".join(lines)
