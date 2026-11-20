"""What a task dispatch tells the agent.

Two layers, so a task session reads like a conversation rather than a manual:

* **The brief** (`TASK_BRIEF`): the standing rules for working on a Vicoa task
  (write to the task, reply in threads, own the status when assigned, ask a
  person with `--ask` when stuck, keeping the task). It rides as the session's system prompt, after
  the agent profile's own instructions, so it never shows in the transcript and
  survives compaction. A session that was not started with it (one a person
  opened and later filed under the task) gets it once, in front of its first
  task message. A session a dispatch started also gets `WORKTREE_RULE`:
  Vicoa chose its folder, so whether the work needs a worktree is the
  agent's call. A session a person started runs where they chose and never
  gets that rule.
* **The message**: what happened, in the user's terms: who assigned the task or
  commented, the comment text itself, and the one command the turn hinges on
  (`--reply-to`). It names the person and quotes them, so whoever watches the
  session sees what the agent sees. The thread on the task stays the record; a
  quoted comment is a snapshot of it.

Two modes: **Ownership** (the task was assigned to the agent) and **Reply** (a
person's comment is for it). Commands are the `vicoa task` CLI every Vicoa
session already has.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

# Longest comment quoted in a message; the rest is in the thread.
QUOTE_LIMIT = 1500

TASK_BRIEF = """\
You also work on Vicoa tasks. A task is a piece of work with a comment thread; \
people hand you one by assigning it to you or by commenting for you, and each \
message about a task says what happened. The task and its thread are the record: \
people follow the task, not this session. Vicoa tasks are reached only through \
the `vicoa task` CLI; they are not your own task or todo tools.

- Read the task and its thread before acting: `vicoa task get <ref>`, \
`vicoa task comments <ref>`.
- Write on the task: progress, results and questions are comments \
(`vicoa task comment <ref> - <<'EOF'` … `EOF`). Answer a comment in its own \
thread with `--reply-to <comment id>`, one reply per thread.
- A task assigned to you is yours to move: `vicoa task update <ref> --status \
in_progress` when you start, `--status in_review` once it is delivered (a PR link \
or the evidence in a comment). Don't set `done` or `cancelled` on your own: a \
person closes the task after looking at what you delivered, or asks you to.
- A task that is not assigned to you: answer what was asked, and leave the \
assignee and the status alone.
- Need a person (a decision, an answer, access)? Ask in one top-level comment \
with `vicoa task comment <ref> --ask`, options first with your recommendation. \
That asks whoever handed you this work; add `--to <person>` to ask someone else. \
If you can't go on without the answer, also set `--status blocked`. Leave the \
assignee alone. A plain comment is not a question: nobody is told to answer it. \
The answer comes back to you here. If `--ask` is not recognised, your CLI is out \
of date: post the question as a plain top-level comment and set `blocked`.\
"""

# Only in a session a dispatch started (`task_brief`). Its folder is the
# task's: the project's own, or the worktree an earlier session on the task
# made. Vicoa never makes a worktree for it, so the agent does when the work
# changes code. Worded for any agent: one CLI command, no agent's own tools.
WORKTREE_RULE = """\
- Changing code in a git repository? Do it in a worktree of its own: \
`vicoa worktree new <name>` (for VIC-42, `vic-42`) makes one, runs the \
repository's worktree setup and files this session under it. Make every change \
in the folder it prints; later sessions on the task start there. Reading, \
answering and planning need no worktree, a session already in one stays there \
(the command says so), and a folder outside git is worked in as it is. If \
`vicoa worktree new` is not recognised, your CLI is out of date: use \
`git worktree add`, then `vicoa session update "$VICOA_AGENT_INSTANCE_ID" \
--worktree <branch>`.\
"""


def task_brief(*, dispatch_started: bool) -> str:
    """The brief for a session: with `WORKTREE_RULE` when a dispatch started it."""
    return f"{TASK_BRIEF}\n{WORKTREE_RULE}" if dispatch_started else TASK_BRIEF


CONTINUITY_NOTE = (
    "Your earlier session on this task could not be resumed, so you start fresh "
    "here. Read the task and its thread before doing anything."
)


@dataclass(frozen=True)
class QuotedComment:
    """A person's comment, as a message quotes it."""

    id: UUID
    # The thread it belongs to (its root): where a reply goes.
    thread_id: UUID
    author: str
    body: str


@dataclass(frozen=True)
class SinceHandover:
    """What happened to a task while it was out of this agent's hands."""

    # When the agent last handed the task over, for people: "2026-11-16 09:12 UTC".
    at: str
    comments: Sequence[QuotedComment] = ()
    # Plain words for other edits since then: "the description was edited".
    edits: Sequence[str] = ()


@dataclass(frozen=True)
class EarlierSession:
    """Earlier work on the task in a session this one doesn't continue."""

    session_id: UUID
    agent_name: str | None = None
    # The worktree this session starts in is that session's.
    same_folder: bool = False


def system_prompt_with_brief(
    profile_prompt: str | None, brief: str = TASK_BRIEF
) -> str:
    """The agent profile's own instructions, then the task brief."""
    own = (profile_prompt or "").strip()
    return f"{own}\n\n{brief}" if own else brief


def with_brief(message: str) -> str:
    """A message for a session that wasn't started with the brief."""
    return (
        "How to work on Vicoa tasks, from now on in this session:\n\n"
        f"{TASK_BRIEF}\n\n---\n\n{message}"
    )


def _quote(body: str) -> str:
    text = body.strip()
    if len(text) > QUOTE_LIMIT:
        text = text[: QUOTE_LIMIT - 1].rstrip() + "… (the rest is in the thread)"
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _task_line(ref: str, title: str) -> str:
    return f'{ref} "{title}"'


def _comment_block(comments: Sequence[QuotedComment]) -> list[str]:
    lines: list[str] = []
    for comment in comments:
        lines.append(f"{comment.author}, in thread `{comment.thread_id}`:")
        lines += _quote(comment.body).splitlines()
        lines.append("")
    return lines


def _reply_line(ref: str, comments: Sequence[QuotedComment]) -> str:
    threads = list(dict.fromkeys(c.thread_id for c in comments))
    if len(threads) == 1:
        return f"Reply in its thread: `vicoa task comment {ref} --reply-to {threads[0]} -`."
    return (
        f"Reply in each thread: `vicoa task comment {ref} --reply-to <thread id> -`, "
        "one reply per thread."
    )


def _earlier_lines(earlier: EarlierSession) -> list[str]:
    who = earlier.agent_name or "You"
    where = " (in this folder, so its changes are here)" if earlier.same_folder else ""
    return [
        "",
        f"{who} worked on it before, in session {earlier.session_id}{where}. Read it "
        f"if you need its reasoning: `vicoa session get {earlier.session_id} --all`.",
    ]


def ownership_prompt(
    *,
    ref: str,
    title: str,
    assigned_by: str | None,
    comments: Sequence[QuotedComment] = (),
    since: SinceHandover | None = None,
    earlier: EarlierSession | None = None,
    continuity: bool = False,
) -> str:
    who = assigned_by or "Someone"
    task = _task_line(ref, title)
    if since is None:
        lines = [
            f"{who} assigned {task} to you.",
            f"Start with `vicoa task get {ref}` and `vicoa task comments {ref}`.",
        ]
        if comments:
            lines += ["", "New comments on it:", ""] + _comment_block(comments)
            lines.append(_reply_line(ref, comments))
    else:
        lines = [
            f"{who} assigned {task} back to you.",
            "",
            f"Since you handed it over ({since.at}):",
            "",
        ]
        lines += _comment_block(since.comments)
        lines += [f"- {edit}" for edit in since.edits]
        if not since.comments and not since.edits:
            lines.append(
                "- nothing was written on the task; the hand-back is the signal."
            )
        if since.edits or not since.comments:
            lines.append("")
        lines.append(
            "The code may have moved too: bring your branch up to date before you continue."
        )
        if since.comments:
            lines.append(_reply_line(ref, since.comments))
    if earlier is not None:
        lines += _earlier_lines(earlier)
    if continuity:
        lines += ["", CONTINUITY_NOTE]
    return "\n".join(lines).rstrip()


# How a single comment reached the agent, for the message's first line.
_VERBS = {
    "mentioned": "mentioned you on",
    "replied": "replied on",
    "commented": "commented on",
    "answered": "answered your question on",
}


def reply_prompt(
    *,
    ref: str,
    title: str,
    trigger: str,
    comments: Sequence[QuotedComment],
    earlier: EarlierSession | None = None,
    continuity: bool = False,
) -> str:
    task = _task_line(ref, title)
    if len(comments) == 1:
        comment = comments[0]
        verb = _VERBS.get(trigger, "commented on")
        lines = [f"{comment.author} {verb} {task}:", "", _quote(comment.body), ""]
    elif comments:
        lines = [f"New comments on {task}:", ""] + _comment_block(comments)
    else:
        # Deleted before the turn came: the thread is all there is.
        lines = [
            f"There are new comments for you on {task}: `vicoa task comments {ref}`.",
            "",
        ]
    if comments:
        lines.append(_reply_line(ref, comments))
    if earlier is not None:
        lines += _earlier_lines(earlier)
    if continuity:
        lines += ["", CONTINUITY_NOTE]
    return "\n".join(lines).rstrip()
