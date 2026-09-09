"""Task identifiers — `projects.key` + `tasks.number` (collaboration §3.5, D-B).

Tasks display Linear-style as **KEY-42**. The two halves are independent
choices that the first draft of the plan conflated:

* counter **scope** → per project (`projects.task_counter`, every project counts
  from 1), so the numbers stay small and a shared board is self-contained;
* display **prefix** → `projects.key`, unique *within the owner* and never
  globally. A global key namespace would re-import the squatting and enumeration
  problems §3.2 avoids for team slugs, and inside one account "VIC-42" is
  already unambiguous.

**Keys are allocated lazily, on a project's first task**, not when the project
is created. Projects are created from three places — the Inbox helper, the
explicit REST create, and the session-registration auto-match, which runs on the
daemon's hot path in the `servers` process — and only the last of those would
have had to grow a uniqueness query and a race it cannot retry out of. Deferring
to `create_task` puts the allocation somewhere that *can* retry, keeps the
registration path untouched, and means a project that never holds a task never
takes a name out of the namespace.
"""

import logging
import re
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .task_models import Project

logger = logging.getLogger(__name__)

# Longest key the column takes. The derived base is 3, so the collision suffix
# has room to run to five digits before it would have to truncate.
MAX_KEY_LENGTH = 8
# Derived base length. Three is the Linear/Jira convention ("VIC", "ENG").
KEY_BASE_LENGTH = 3
# Generic base for a name with nothing ASCII to derive from — CJK names, emoji
# names, "工作". Mangling those into initials produces noise, so they get a
# neutral key and the user renames it in project settings if they care.
FALLBACK_KEY_BASE = "PRJ"

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")
_LEADING_DIGITS = re.compile(r"^[0-9]+")
# "VIC-42" / "vic-42". The key half is bounded by MAX_KEY_LENGTH so a stray
# "AB-1234567890123" can't turn into a pathological lookup.
_IDENTIFIER = re.compile(r"^\s*([A-Za-z][A-Za-z0-9]{1,7})-([0-9]{1,9})\s*$")


def derive_key_base(name: str) -> str:
    """The un-deduplicated key a project name suggests.

    Uppercase, ASCII alnum only, leading digits dropped (a key that starts with
    a number reads as part of the number), truncated to `KEY_BASE_LENGTH`.
    Anything that leaves fewer than two usable characters falls back.
    """
    stripped = _NON_ALNUM.sub("", name or "")
    stripped = _LEADING_DIGITS.sub("", stripped)
    base = stripped[:KEY_BASE_LENGTH].upper()
    return base if len(base) >= 2 else FALLBACK_KEY_BASE


def _taken_keys(db: Session, user_id: UUID) -> set[str]:
    """Every key already spoken for by this owner, uppercased.

    P3 adds `projects.team_id`; when it does, a team-owned project's namespace
    is the team's, and this predicate grows a branch. Until then there is only
    one kind of owner.
    """
    rows = db.execute(
        select(func.upper(Project.key)).where(
            Project.user_id == user_id, Project.key.is_not(None)
        )
    ).all()
    return {row[0] for row in rows if row[0]}


def next_free_key(db: Session, user_id: UUID, name: str, *, attempt: int = 0) -> str:
    """A key for `name` that no other project of this owner holds.

    `attempt` shifts the starting suffix so a caller retrying after a lost race
    doesn't re-propose the candidate that just collided.
    """
    base = derive_key_base(name)
    taken = _taken_keys(db, user_id)
    if attempt == 0 and base not in taken:
        return base
    # BASE, BASE2, BASE3 … — the same shape Linear uses, and short enough that
    # the suffix never pushes past MAX_KEY_LENGTH in practice.
    suffix = max(attempt, 1) + 1
    while True:
        candidate = f"{base}{suffix}"[:MAX_KEY_LENGTH]
        if candidate not in taken:
            return candidate
        suffix += 1


def allocate_task_number(db: Session, project: Project) -> int:
    """Take the next number in `project`, bumping the counter atomically.

    `UPDATE … RETURNING` on the counter column: the row lock it takes is held to
    the end of the transaction, so two concurrent inserts into the same project
    serialize instead of both reading the same value. A per-project sequence is
    not an option (sequences are schema objects, not rows).
    """
    number = db.execute(
        update(Project)
        .where(Project.id == project.id)
        .values(task_counter=Project.task_counter + 1)
        .returning(Project.task_counter)
    ).scalar_one()
    # The ORM copy still holds the pre-UPDATE value; expire it so anything that
    # reads `project.task_counter` later in this session sees the real one.
    db.expire(project, ["task_counter"])
    return int(number)


def format_task_identifier(key: str | None, number: int | None) -> str | None:
    """ "VIC-42", or None when the task predates its project's key/backfill."""
    if not key or number is None:
        return None
    return f"{key}-{number}"


def parse_task_identifier(value: str) -> tuple[str, int] | None:
    """Split "VIC-42" into ("VIC", 42). None when it isn't an identifier.

    Lets every task-by-id surface — the REST path param, `vicoa task get`, the
    web route — accept the identifier a human (or an agent reading it out of a
    prompt) actually has in hand, not just a UUID.
    """
    match = _IDENTIFIER.match(value)
    if match is None:
        return None
    return match.group(1).upper(), int(match.group(2))


# How many keys to try before giving up. A collision needs two projects of the
# same owner, with names deriving to the same base, inserted concurrently — so
# in practice the first attempt always wins and this only bounds pathology.
KEY_ALLOCATION_ATTEMPTS = 5


def ensure_project_key_committed(db: Session, project: Project) -> str | None:
    """Give `project` a key, retrying past a lost uniqueness race.

    Runs in a SAVEPOINT so a collision rolls back the key write **and nothing
    else** — the caller is usually mid-way through creating or moving a task,
    and a plain rollback would take that with it. Same shape as
    `get_or_create_inbox`, for the same reason.

    Returns None if every attempt collided: the task still gets its number and
    simply renders without an identifier until someone sets a key by hand. A
    project without a key is a cosmetic problem; a failed task create is not.
    """
    if project.key:
        return project.key

    for attempt in range(KEY_ALLOCATION_ATTEMPTS):
        nested = db.begin_nested()
        try:
            project.key = next_free_key(
                db, project.user_id, project.name, attempt=attempt
            )
            db.flush()
            nested.commit()
            return project.key
        except IntegrityError:
            nested.rollback()
            logger.info(
                "project key race for project %s (attempt %d)", project.id, attempt + 1
            )
    logger.warning("could not allocate a task key for project %s", project.id)
    return None
