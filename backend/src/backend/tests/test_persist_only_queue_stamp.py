"""A persist-only artifact is never stamped `queued`.

`POST /agent-instances/{id}/messages` stamps `queue.status = "queued"` on a
message sent while the session is ACTIVE, and clears it to `consumed` when the
agent picks the message up. The AskUserQuestion answer summary and the
"Declined to answer" note are `action: persist_only` artifacts that every
runner acks without consuming, so a `queued` stamp on one never clears, and
both clients hide pending user messages from the transcript: the user's
answer disappeared although the agent had it.
"""

import base64
import json

import pytest

from shared.database.enums import AgentStatus


def _summary_message(question: str, label: str) -> str:
    """The answer summary exactly as the web and mobile pickers build it."""
    payload = {
        "message_id": "prompt-message-id",
        "answers": [{"mode": "option", "option_index": 0}],
        "display_answers": [{"question": question, "header": "Q1", "label": label}],
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    control = json.dumps(
        {
            "type": "control",
            "action": "persist_only",
            "kind": "ask_user_question_summary",
            "value": f"v1:{encoded}",
        },
        separators=(",", ":"),
    )
    return f"Q: {question}\nA: {label}\n{control}"


DECLINED_MESSAGE = 'Declined to answer\n{"type":"control","action":"persist_only"}'


def _send(client, instance_id, content: str) -> dict:
    response = client.post(
        f"/api/v1/agent-instances/{instance_id}/messages",
        json={"content": content},
    )
    assert response.status_code == 200
    return response.json()


def _queue_status(body: dict) -> str | None:
    return ((body.get("message_metadata") or {}).get("queue") or {}).get("status")


@pytest.mark.parametrize(
    "content",
    [
        _summary_message("Which database?", "Postgres"),
        DECLINED_MESSAGE,
    ],
    ids=["answer-summary", "declined"],
)
def test_persist_only_artifact_is_not_queued_while_active(
    authenticated_client, test_agent_instance, content
):
    assert test_agent_instance.status == AgentStatus.ACTIVE

    body = _send(authenticated_client, test_agent_instance.id, content)

    assert _queue_status(body) is None
    detail = authenticated_client.get(
        f"/api/v1/agent-instances/{test_agent_instance.id}"
    ).json()
    stored = next(m for m in detail["messages"] if m["id"] == body["id"])
    assert _queue_status(stored) is None


@pytest.mark.parametrize(
    "content",
    [
        "keep going while you work",
        # Real input that quotes a persist_only token mid-body is delivered to
        # the agent, so it still queues like any other message.
        'what does {"type":"control","action":"persist_only"} mean here?',
        # The answer directive itself is routed to the open question, not
        # through this change.
        'Submit AskUserQuestion answers. {"type":"control",'
        '"setting":"ask_user_question","value":"submit:e30"}',
    ],
    ids=["plain", "quoted-token", "auq-submit-directive"],
)
def test_other_messages_still_queue_while_active(
    authenticated_client, test_agent_instance, content
):
    assert test_agent_instance.status == AgentStatus.ACTIVE

    body = _send(authenticated_client, test_agent_instance.id, content)

    assert _queue_status(body) == "queued"


def test_persist_only_artifact_unchanged_when_not_active(
    authenticated_client, test_db, test_agent_instance
):
    test_agent_instance.status = AgentStatus.AWAITING_INPUT
    test_db.commit()

    body = _send(
        authenticated_client,
        test_agent_instance.id,
        _summary_message("Which database?", "Postgres"),
    )

    assert _queue_status(body) is None
