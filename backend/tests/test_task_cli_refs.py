"""Unit tests for what the ``vicoa task`` / ``project`` / ``label`` handlers
*build* from a project key, a label name, or a list of task refs.

The endpoints are covered in ``servers/tests``; what is only reachable here is
the client-side resolution — ``--project VIC`` / ``--project none``, ``--label
growth`` — and the bulk ``task update`` loop with its ``VIC-20 → VIC2-2``
rename line and keep-going-on-404 behaviour.
"""

import json
import types

import pytest

from vicoa.commands import label as L
from vicoa.commands import project as P
from vicoa.commands import task as T
from vicoa.commands._api import RequestError

PROJECTS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "key": "VIC",
        "name": "Acme",
        "is_archived": False,
        "directories": [{"machine_id": "m1", "local_path": "/home/me/acme"}],
        "task_count": 3,
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "key": "VIC2",
        "name": "Growth",
        "is_archived": False,
        "directories": [],
        "task_count": 0,
    },
]
LABELS = [
    {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "name": "growth",
        "color": "#ff0000",
    },
    {"id": "aaaaaaaa-0000-0000-0000-000000000002", "name": "bug", "color": "#00ff00"},
]


def _args(**over):
    base = {"json": False, "api_key": "k", "base_url": None}
    base.update(over)
    return types.SimpleNamespace(**base)


class FakeServer:
    """Answers the handful of routes the handlers touch and records writes."""

    def __init__(self, tasks=None):
        self.tasks = {t["id"]: t for t in (tasks or [])}
        for t in list(self.tasks.values()):
            if t.get("identifier"):
                self.tasks[t["identifier"]] = t
        self.sent: list[tuple[str, str, dict | None, dict | None]] = []

    def __call__(
        self, args, api_key, method, endpoint, *, params=None, json=None, **kw
    ):
        self.sent.append((method, endpoint, params, json))
        if endpoint == "/api/v1/projects":
            return PROJECTS
        if endpoint.startswith("/api/v1/projects/"):
            ref = endpoint.rsplit("/", 1)[1]
            for p in PROJECTS:
                if p["id"] == ref:
                    return p
            raise RequestError(404, "Project not found")
        if endpoint == "/api/v1/task-labels":
            if method == "POST":
                return {"id": "new-label", **(json or {})}
            return LABELS
        if endpoint == "/api/v1/tasks":
            if method == "POST":
                return {"id": "new", "identifier": "VIC-9", **(json or {})}
            return list({id(t): t for t in self.tasks.values()}.values())
        if endpoint.startswith("/api/v1/tasks/"):
            ref = endpoint.rsplit("/", 1)[1]
            task = self.tasks.get(ref)
            if task is None:
                if kw.get("raise_on_error"):
                    raise RequestError(404, "Task not found")
                raise SystemExit(1)
            if method == "PATCH":
                updated = dict(task)
                updated.update(json or {})
                if "project_id" in (json or {}):
                    target = next(
                        (p for p in PROJECTS if p["id"] == json["project_id"]), None
                    )
                    updated["identifier"] = f"{target['key']}-7" if target else None
                if "label_ids" in (json or {}):
                    updated["labels"] = [
                        lbl for lbl in LABELS if lbl["id"] in json["label_ids"]
                    ]
                return updated
            return task
        raise AssertionError(f"unexpected {method} {endpoint}")


@pytest.fixture
def server(monkeypatch):
    srv = FakeServer(
        tasks=[
            {
                "id": "t-20",
                "identifier": "VIC-20",
                "title": "Twenty",
                "project_id": PROJECTS[0]["id"],
                "labels": [LABELS[1]],
            },
            {
                "id": "t-21",
                "identifier": "VIC-21",
                "title": "Twenty-one",
                "project_id": PROJECTS[0]["id"],
                "labels": [],
            },
        ]
    )
    monkeypatch.setattr(T, "_request", srv)
    monkeypatch.setattr(P, "request", srv)
    monkeypatch.setattr(L, "request", srv)
    return srv


class TestProjectRef:
    def test_key_resolves_case_insensitively(self, server):
        assert P.resolve_project_ref(_args(), "k", "vic2") == PROJECTS[1]["id"]

    def test_name_resolves(self, server):
        assert P.resolve_project_ref(_args(), "k", "growth") == PROJECTS[1]["id"]

    def test_uuid_passes_through_with_one_get(self, server):
        assert (
            P.resolve_project_ref(_args(), "k", PROJECTS[0]["id"]) == PROJECTS[0]["id"]
        )
        assert server.sent[-1][1] == f"/api/v1/projects/{PROJECTS[0]['id']}"

    def test_none_is_no_project(self, server):
        assert P.resolve_project_ref(_args(), "k", "none") is None
        assert server.sent == []  # no lookup needed

    def test_unknown_ref_exits_2_naming_the_projects(self, server, capsys):
        with pytest.raises(SystemExit) as exc:
            P.resolve_project_ref(_args(), "k", "nope")
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "no project with key or name 'nope'" in err
        assert "VIC" in err and "VIC2" in err

    def test_ambiguous_name_exits_2(self, server, monkeypatch):
        twin = dict(PROJECTS[1], id="33333333-3333-3333-3333-333333333333", key="GR2")
        monkeypatch.setattr(P, "_list_projects", lambda *a, **k: PROJECTS + [twin])
        with pytest.raises(SystemExit) as exc:
            P.resolve_project_ref(_args(), "k", "Growth")
        assert exc.value.code == 2


class TestLabelRef:
    def test_names_resolve_to_ids_with_one_get(self, server):
        ids = L.resolve_label_names(_args(), "k", ["Growth", "bug"])
        assert ids == [LABELS[0]["id"], LABELS[1]["id"]]
        assert [s[1] for s in server.sent] == ["/api/v1/task-labels"]

    def test_unknown_label_exits_2(self, server, capsys):
        with pytest.raises(SystemExit):
            L.resolve_label_names(_args(), "k", ["nope"])
        assert "vicoa label create" in capsys.readouterr().err

    def test_create_uses_the_webs_colour_for_the_name(self, server):
        # Same hash → palette rule as apps/web inlineLabelColor.
        assert L.inline_label_color("growth") == L.inline_label_color("growth")
        assert L.inline_label_color("growth") in L._INLINE_LABEL_COLORS
        assert L._cmd_create(_args(name="ops", color=None), "k") == 0
        method, endpoint, _, body = server.sent[-1]
        assert (method, endpoint) == ("POST", "/api/v1/task-labels")
        assert body == {"name": "ops", "color": L.inline_label_color("ops")}

    def test_create_refuses_a_duplicate_name(self, server, capsys):
        assert L._cmd_create(_args(name="Growth", color=None), "k") == 1
        assert not any(m == "POST" for m, *_ in server.sent)
        assert "already exists" in capsys.readouterr().err


class TestTaskLs:
    def test_project_key_becomes_project_id(self, server):
        T._cmd_ls(_args(project="VIC", status=None, priority=None, label=None), "k")
        method, endpoint, params, _ = server.sent[-1]
        assert endpoint == "/api/v1/tasks"
        assert params == {"project_id": PROJECTS[0]["id"]}

    def test_project_none_becomes_unfiled(self, server):
        T._cmd_ls(_args(project="none", status=None, priority=None, label=None), "k")
        assert server.sent[-1][2] == {"unfiled": "true"}

    def test_labels_become_label_ids(self, server):
        T._cmd_ls(
            _args(project=None, status=None, priority=None, label=["growth", "bug"]),
            "k",
        )
        assert server.sent[-1][2] == {"label_id": [LABELS[0]["id"], LABELS[1]["id"]]}

    def test_table_has_a_project_column(self, server, capsys):
        T._cmd_ls(_args(project=None, status=None, priority=None, label=None), "k")
        out = capsys.readouterr().out
        assert "PROJECT" in out.splitlines()[0]

    def test_project_column_falls_back_to_the_key_on_an_old_server(self):
        assert T._project_label({"project_id": "x", "identifier": "VIC-3"}) == "VIC"
        assert T._project_label({"project_id": "x", "project_name": "Acme"}) == ("Acme")
        assert T._project_label({"project_id": None}) == "—"


class TestTaskCreate:
    def test_project_and_labels(self, server):
        T._cmd_create(
            _args(
                title="New",
                description=None,
                project="growth",
                status=None,
                priority=None,
                parent=None,
                label=["bug"],
                start=None,
                due=None,
            ),
            "k",
        )
        _, endpoint, _, body = server.sent[-1]
        assert endpoint == "/api/v1/tasks"
        assert body["project_id"] == PROJECTS[1]["id"]
        assert body["label_ids"] == [LABELS[1]["id"]]

    def test_project_none_files_under_no_project(self, server):
        T._cmd_create(
            _args(
                title="Loose",
                description=None,
                project="none",
                status=None,
                priority=None,
                parent=None,
                label=None,
                start=None,
                due=None,
            ),
            "k",
        )
        assert "project_id" not in server.sent[-1][3]


def _update_args(*refs, **over):
    base = {
        "task_ids": list(refs),
        "title": None,
        "description": None,
        "project": None,
        "status": None,
        "priority": None,
        "parent": None,
        "start": None,
        "due": None,
        "label": None,
        "add_label": None,
        "remove_label": None,
    }
    base.update(over)
    return _args(**base)


class TestTaskUpdate:
    def test_single_ref_plain_field_is_one_patch(self, server, capsys):
        assert T._cmd_update(_update_args("VIC-20", status="done"), "k") == 0
        patches = [s for s in server.sent if s[0] == "PATCH"]
        assert patches == [("PATCH", "/api/v1/tasks/VIC-20", None, {"status": "done"})]
        assert "Updated task VIC-20: Twenty" in capsys.readouterr().out

    def test_several_refs_get_the_same_patch(self, server):
        assert (
            T._cmd_update(_update_args("VIC-20", "VIC-21", priority="high"), "k") == 0
        )
        patches = [s[1] for s in server.sent if s[0] == "PATCH"]
        assert patches == ["/api/v1/tasks/VIC-20", "/api/v1/tasks/VIC-21"]

    def test_move_prints_the_new_identifier(self, server, capsys):
        assert T._cmd_update(_update_args("VIC-20", "VIC-21", project="VIC2"), "k") == 0
        out = capsys.readouterr().out
        assert "Updated task VIC-20 → VIC2-7: Twenty" in out
        assert "Updated task VIC-21 → VIC2-7: Twenty-one" in out
        body = [s[3] for s in server.sent if s[0] == "PATCH"][0]
        assert body == {"project_id": PROJECTS[1]["id"]}

    def test_move_to_none_sends_an_explicit_null(self, server, capsys):
        assert T._cmd_update(_update_args("VIC-20", project="none"), "k") == 0
        body = [s[3] for s in server.sent if s[0] == "PATCH"][0]
        assert body == {"project_id": None}
        # The identifier is gone, so the rename line falls back to the id.
        assert "Updated task VIC-20 → t-20: Twenty" in capsys.readouterr().out

    def test_a_missing_ref_is_reported_and_the_rest_still_run(self, server, capsys):
        rc = T._cmd_update(
            _update_args("VIC-20", "VIC-99", "VIC-21", status="todo"), "k"
        )
        assert rc == 1
        # All three were attempted — the 404 in the middle did not stop the loop.
        patched = [s[1] for s in server.sent if s[0] == "PATCH"]
        assert patched == [
            "/api/v1/tasks/VIC-20",
            "/api/v1/tasks/VIC-99",
            "/api/v1/tasks/VIC-21",
        ]
        captured = capsys.readouterr()
        assert "VIC-99: Task not found (HTTP 404)" in captured.err
        assert captured.out.count("Updated task") == 2

    def test_add_label_keeps_existing_labels(self, server):
        assert T._cmd_update(_update_args("VIC-20", add_label=["growth"]), "k") == 0
        body = [s[3] for s in server.sent if s[0] == "PATCH"][0]
        # bug (already on the task) stays, growth is appended.
        assert body == {"label_ids": [LABELS[1]["id"], LABELS[0]["id"]]}

    def test_remove_label_drops_only_that_one(self, server):
        assert T._cmd_update(_update_args("VIC-20", remove_label=["bug"]), "k") == 0
        body = [s[3] for s in server.sent if s[0] == "PATCH"][0]
        assert body == {"label_ids": []}

    def test_label_replaces_the_set_without_a_read(self, server):
        assert T._cmd_update(_update_args("VIC-20", label=["growth"]), "k") == 0
        assert not any(s[0] == "GET" and "/tasks/" in s[1] for s in server.sent)
        body = [s[3] for s in server.sent if s[0] == "PATCH"][0]
        assert body == {"label_ids": [LABELS[0]["id"]]}

    def test_nothing_to_update_is_2(self, server, capsys):
        assert T._cmd_update(_update_args("VIC-20"), "k") == 2
        assert server.sent == []

    def test_json_single_is_an_object_many_is_a_list(self, server, capsys):
        T._cmd_update(_update_args("VIC-20", status="done", json=True), "k")
        assert isinstance(json.loads(capsys.readouterr().out), dict)
        T._cmd_update(_update_args("VIC-20", "VIC-21", status="done", json=True), "k")
        assert len(json.loads(capsys.readouterr().out)) == 2


class TestProjectCommands:
    def test_ls_table(self, server, capsys, monkeypatch):
        monkeypatch.setattr(P, "_local_machine_id", lambda args: "m1")
        assert P._cmd_ls(_args(include_archived=False), "k") == 0
        out = capsys.readouterr().out
        head = out.splitlines()[0]
        for col in ("ID", "KEY", "NAME", "PATH", "TASKS"):
            assert col in head
        assert "VIC " in out and "/home/me/acme" in out and "Acme" in out
        assert "2 project(s)." in out

    def test_get_by_key_prints_detail(self, server, capsys):
        assert P._cmd_get(_args(project="vic2"), "k") == 0
        out = capsys.readouterr().out
        assert f"id:          {PROJECTS[1]['id']}" in out
        assert "key:         VIC2" in out


class TestOldServerGuard:
    """A backend without `unfiled`/`label_id` returns the whole backlog; the
    CLI re-filters so `--project none` / `--label` stay honest."""

    def test_unfiled_is_reapplied_locally(self):
        rows = [{"project_id": None, "labels": []}, {"project_id": "p", "labels": []}]
        assert T._apply_filters_locally(rows, "true", []) == [rows[0]]

    def test_labels_are_reapplied_locally(self):
        rows = [
            {"project_id": "p", "labels": [{"id": "a"}, {"id": "b"}]},
            {"project_id": "p", "labels": [{"id": "a"}]},
        ]
        assert T._apply_filters_locally(rows, None, ["a", "b"]) == [rows[0]]

    def test_no_filters_is_a_no_op(self):
        rows = [{"project_id": None}]
        assert T._apply_filters_locally(rows, None, []) is rows
