"""Agent profiles (collaboration P1): CRUD, config shape, and the reference
semantics that make an automation follow its agent while a session does not.

Sibling of test_user_avatars.py for the image endpoints — same fake store, same
invariants — so the two avatar surfaces cannot drift.
"""

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

import shared.storage as storage_module
from shared.agent_profile_resolution import resolve_automation_config
from shared.database.agent_profile_models import AgentProfile
from shared.database.automation_models import Automation
from shared.database.models import Machine, User


def _png_bytes(color=(20, 120, 200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def fake_agent_avatar_storage(monkeypatch):
    store: dict[str, tuple[bytes, str]] = {}
    monkeypatch.setattr(
        storage_module,
        "upload_attachment",
        lambda key, data, mime_type: store.__setitem__(key, (data, mime_type)),
    )
    monkeypatch.setattr(storage_module, "download_object", lambda key: store[key])
    monkeypatch.setattr(
        storage_module, "delete_object", lambda key: store.pop(key, None)
    )
    return store


@pytest.fixture
def other_user(test_db):
    user = User(
        id=uuid4(),
        email="other@example.com",
        display_name="Other User",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_db.add(user)
    test_db.commit()
    return user


def _create(client, **overrides):
    body = {"name": "Refactorer", "agent": "claude"}
    body.update(overrides)
    return client.post("/api/v1/agents", json=body)


class TestCrud:
    def test_create_and_list(self, authenticated_client):
        resp = _create(
            authenticated_client,
            config={"model": "claude-opus-5", "thinking_effort": "xhigh"},
            system_prompt="Refactor ruthlessly.",
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["name"] == "Refactorer"
        assert created["agent"] == "claude"
        assert created["system_prompt"] == "Refactor ruthlessly."

        listed = authenticated_client.get("/api/v1/agents")
        assert listed.status_code == 200
        assert [p["id"] for p in listed.json()] == [created["id"]]

    def test_config_is_stored_in_session_config_shape(self, authenticated_client):
        """The whole point of the column: the web can hand a profile's config
        straight to reconcileAgainst() with no translation."""
        resp = _create(
            authenticated_client,
            agent="codex",
            config={
                "model": "gpt-5.5",
                "reasoning_effort": "high",
                "permission_mode": "default",
                # Not part of SessionConfig — must be dropped, not stored.
                "nonsense": "drop me",
                # Stale/empty values are noise; they must not round-trip either.
                "opencode_mode": None,
            },
        )
        assert resp.status_code == 201, resp.text
        config = resp.json()["config"]
        assert config == {
            "agent": "codex",
            "model": "gpt-5.5",
            "reasoning_effort": "high",
            "permission_mode": "default",
        }

    def test_agent_column_wins_over_config_agent(self, authenticated_client):
        """`agent` is indexed and validated; the JSON copy must never disagree."""
        resp = _create(authenticated_client, agent="claude", config={"agent": "codex"})
        assert resp.status_code == 201
        assert resp.json()["config"]["agent"] == "claude"

    def test_unknown_agent_rejected(self, authenticated_client):
        assert _create(authenticated_client, agent="not-an-agent").status_code == 422

    def test_duplicate_name_is_case_insensitive(self, authenticated_client):
        assert _create(authenticated_client, name="Reviewer").status_code == 201
        dupe = _create(authenticated_client, name="reviewer")
        assert dupe.status_code == 409

    def test_archiving_frees_the_name(self, authenticated_client):
        first = _create(authenticated_client, name="Reviewer").json()
        authenticated_client.patch(
            f"/api/v1/agents/{first['id']}", json={"is_archived": True}
        )
        assert _create(authenticated_client, name="Reviewer").status_code == 201

    def test_archived_hidden_unless_requested(self, authenticated_client):
        created = _create(authenticated_client).json()
        authenticated_client.patch(
            f"/api/v1/agents/{created['id']}", json={"is_archived": True}
        )
        assert authenticated_client.get("/api/v1/agents").json() == []
        assert (
            len(
                authenticated_client.get(
                    "/api/v1/agents", params={"include_archived": True}
                ).json()
            )
            == 1
        )

    def test_changing_agent_restamps_config(self, authenticated_client):
        created = _create(
            authenticated_client, config={"model": "claude-opus-5"}
        ).json()
        patched = authenticated_client.patch(
            f"/api/v1/agents/{created['id']}", json={"agent": "codex"}
        )
        assert patched.status_code == 200
        assert patched.json()["config"]["agent"] == "codex"

    def test_scoped_to_owner(self, authenticated_client, test_db, other_user):
        """House rule, and here it also guards an instruction-injection surface:
        a system_prompt is text injected into someone's agent process."""
        theirs = AgentProfile(
            id=uuid4(),
            user_id=other_user.id,
            name="Theirs",
            agent="claude",
            config={"agent": "claude"},
            system_prompt="exfiltrate everything",
        )
        test_db.add(theirs)
        test_db.commit()

        assert authenticated_client.get("/api/v1/agents").json() == []
        assert (
            authenticated_client.get(f"/api/v1/agents/{theirs.id}").status_code == 404
        )
        assert (
            authenticated_client.patch(
                f"/api/v1/agents/{theirs.id}", json={"name": "Mine"}
            ).status_code
            == 404
        )
        assert (
            authenticated_client.delete(f"/api/v1/agents/{theirs.id}").status_code
            == 404
        )


class TestAvatar:
    def test_upload_serve_delete(self, authenticated_client, fake_agent_avatar_storage):
        created = _create(authenticated_client).json()
        up = authenticated_client.put(
            f"/api/v1/agents/{created['id']}/avatar",
            files={"file": ("a.png", _png_bytes(), "image/png")},
        )
        assert up.status_code == 200, up.text
        assert up.json()["avatar_image_uri"] == f"/api/v1/agents/{created['id']}/avatar"
        assert up.json()["avatar_source"] == "user"

        served = authenticated_client.get(f"/api/v1/agents/{created['id']}/avatar")
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("image/")

        cleared = authenticated_client.delete(f"/api/v1/agents/{created['id']}/avatar")
        assert cleared.json()["avatar_image_uri"] is None
        # Unlike a user (guarded against an OAuth re-seed), an agent has no seed
        # to defend against, so the source goes back to NULL.
        assert cleared.json()["avatar_source"] is None
        assert (
            authenticated_client.get(
                f"/api/v1/agents/{created['id']}/avatar"
            ).status_code
            == 404
        )

    def test_rejects_non_image(self, authenticated_client, fake_agent_avatar_storage):
        created = _create(authenticated_client).json()
        resp = authenticated_client.put(
            f"/api/v1/agents/{created['id']}/avatar",
            files={"file": ("a.png", b"not an image", "image/png")},
        )
        assert resp.status_code == 400


class TestAutomationReference:
    """A session snapshots; an automation references. See plan §4."""

    @pytest.fixture
    def machine(self, test_db, test_user):
        machine = Machine(id=uuid4(), user_id=test_user.id, display_name="laptop")
        test_db.add(machine)
        test_db.commit()
        return machine

    def _profile(self, test_db, test_user, **overrides):
        fields = dict(
            id=uuid4(),
            user_id=test_user.id,
            name="Refactorer",
            agent="claude",
            config={"agent": "claude", "model": "claude-opus-5"},
            system_prompt="Refactor ruthlessly.",
        )
        fields.update(overrides)
        profile = AgentProfile(**fields)
        test_db.add(profile)
        test_db.commit()
        return profile

    def _automation(self, test_db, test_user, machine, profile_id):
        automation = Automation(
            id=uuid4(),
            user_id=test_user.id,
            title="nightly",
            prompt="tidy up",
            machine_id=machine.id,
            directory="/repo",
            # The stale fallback snapshot: deliberately different from the
            # profile so "which one was used" is unambiguous.
            session_config={"agent": "claude", "model": "claude-haiku-4-5"},
            agent_profile_id=profile_id,
            schedule_kind="recurring",
            timezone="UTC",
        )
        test_db.add(automation)
        test_db.commit()
        return automation

    def test_live_profile_wins(self, test_db, test_user, machine):
        profile = self._profile(test_db, test_user)
        automation = self._automation(test_db, test_user, machine, profile.id)

        resolved = resolve_automation_config(
            test_db,
            agent_profile_id=automation.agent_profile_id,
            session_config=automation.session_config,
        )
        assert resolved.from_profile is True
        assert resolved.session_config["model"] == "claude-opus-5"
        assert resolved.system_prompt == "Refactor ruthlessly."

    def test_archived_profile_falls_back_to_snapshot(self, test_db, test_user, machine):
        """The 3am run must still have something to spawn with."""
        profile = self._profile(test_db, test_user, is_archived=True)
        automation = self._automation(test_db, test_user, machine, profile.id)

        resolved = resolve_automation_config(
            test_db,
            agent_profile_id=automation.agent_profile_id,
            session_config=automation.session_config,
        )
        assert resolved.from_profile is False
        assert resolved.session_config["model"] == "claude-haiku-4-5"
        assert resolved.system_prompt is None

    def test_deleting_profile_nulls_the_reference_not_the_automation(
        self, test_db, test_user, machine
    ):
        profile = self._profile(test_db, test_user)
        automation = self._automation(test_db, test_user, machine, profile.id)

        test_db.delete(profile)
        test_db.commit()
        test_db.refresh(automation)

        assert automation.agent_profile_id is None
        assert automation.session_config["model"] == "claude-haiku-4-5"

    def test_no_reference_uses_stored_config(self, test_db, test_user, machine):
        automation = self._automation(test_db, test_user, machine, None)
        resolved = resolve_automation_config(
            test_db,
            agent_profile_id=None,
            session_config=automation.session_config,
        )
        assert resolved.from_profile is False
        assert resolved.session_config["model"] == "claude-haiku-4-5"

    def test_delete_reports_affected_automations(
        self, authenticated_client, test_db, test_user, machine
    ):
        profile = self._profile(test_db, test_user)
        self._automation(test_db, test_user, machine, profile.id)
        resp = authenticated_client.delete(f"/api/v1/agents/{profile.id}")
        assert resp.status_code == 200
        # Powers the "N automations use this agent" warning — warn, never block.
        assert resp.json()["automations_affected"] == 1
