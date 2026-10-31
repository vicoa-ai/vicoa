"""A working seed for `stack-preview.sh seed`. Copy it into the state dir, swap in
the data your change needs, run `stack-preview.sh seed FILE`.

Two halves: a project and tasks through the API, as Ada (the same code the
reviewer's clicks run), then a session with a short conversation written to the
database, because no endpoint creates a session that already has history.
Invented data only: the preview URL is public.
"""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import UUID

import shared.database.agent_profile_models  # noqa: F401  (older branches fail to flush without it)
from shared.database.agent_instances import get_or_create_agent_type
from shared.database.enums import AgentStatus, SenderType
from shared.database.models import AgentInstance, Message, User
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

API, TOKEN = os.environ["PREVIEW_BACKEND"], os.environ["OWNER_TOKEN"]


def api(path: str, body: dict) -> dict:
    request = urllib.request.Request(
        f"{API}/api/v1{path}",
        json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


project = api("/projects", {"name": "Acme Shop"})
for title, status in [
    ("Fix the login timeout", "in_progress"),
    ("Add a sale banner", "backlog"),
]:
    api("/tasks", {"title": title, "project_id": project["id"], "status": status})

now = datetime.now(timezone.utc)
with Session(create_engine(os.environ["DATABASE_URL"])) as db:
    owner = db.query(User).filter(User.email == os.environ["OWNER_EMAIL"]).one()
    session = AgentInstance(
        user_id=owner.id,
        agent_type_id=get_or_create_agent_type(db, owner.id, "claude code").id,
        project_id=UUID(
            project["id"]
        ),  # what groups it under the project in the sidebar
        project="/Users/ada/work/acme-shop",  # path string; the sidebar's fallback grouping
        name="Fix the login timeout",
        # COMPLETED means archived: default lists and share links hide it.
        status=AgentStatus.AWAITING_INPUT,
        started_at=now - timedelta(minutes=20),
    )
    db.add(session)
    db.flush()
    db.add_all(
        [
            Message(
                agent_instance_id=session.id,
                sender_type=SenderType.USER,
                sender_user_id=owner.id,
                content="Users get logged out after about five minutes. Find out why.",
                created_at=now - timedelta(minutes=19),
            ),
            Message(
                agent_instance_id=session.id,
                sender_type=SenderType.AGENT,
                content="The session cookie expires before the refresh call. The fix is ready; push it?",
                requires_user_input=True,
                created_at=now - timedelta(minutes=2),
            ),
        ]
    )
    print("seeded project", project["id"], "and session", session.id)
    db.commit()
