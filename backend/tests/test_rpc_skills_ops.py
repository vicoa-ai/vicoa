"""Tests for the Skills tab RPC handlers (`list-skills`/`install-skill`/`uninstall-skill`)."""

import json
import subprocess
from pathlib import Path

import pytest

from vicoa.rpc import skills_ops


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


def _write_skill(
    skill_dir: Path, name: str, description: str, *, body: str = "Body."
) -> None:
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def _make_skill_repo(
    tmp_path: Path, *, name: str, extra: dict[str, str] | None = None
) -> Path:
    """A local git repo whose root is a skill; returns a `file://` clonable path."""
    repo = tmp_path / f"repo-{name}"
    _write_skill(repo, name, f"{name} from a repo")
    for rel, content in (extra or {}).items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "x"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, env={**env})
    return repo


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------


def test_list_skills_reports_hand_installed_claude_skill(home: Path):
    _write_skill(home / ".claude" / "skills" / "hello", "hello", "says hi")
    result = skills_ops.list_skills("claude")
    assert result["supported"] is True
    (skill,) = result["skills"]
    assert skill["name"] == "hello"
    assert skill["description"] == "says hi"
    assert skill["scope"] == "user"
    assert skill["source"] is None  # no manifest entry -> unknown provenance
    assert skill["path"].endswith("/.claude/skills/hello")


def test_list_skills_codex_reads_own_and_shared_roots(home: Path):
    _write_skill(home / ".agents" / "skills" / "cross", "cross", "cross-agent")
    _write_skill(home / ".codex" / "skills" / "native", "native", "codex-native")
    names = {s["name"]: s for s in skills_ops.list_skills("codex")["skills"]}
    assert names["cross"]["scope"] == "shared"  # ~/.agents/skills
    assert names["native"]["scope"] == "user"  # ~/.codex/skills


def test_list_skills_claude_does_not_read_agents_shared(home: Path):
    # ~/.agents/skills is NOT read by Claude Code natively — must not leak in.
    _write_skill(home / ".agents" / "skills" / "shared-only", "shared-only", "x")
    _write_skill(home / ".claude" / "skills" / "mine", "mine", "y")
    names = {s["name"] for s in skills_ops.list_skills("claude")["skills"]}
    assert names == {"mine"}


def test_list_skills_opencode_supported(home: Path):
    _write_skill(
        home / ".config" / "opencode" / "skills" / "oc", "oc", "opencode skill"
    )
    result = skills_ops.list_skills("opencode")
    assert result["supported"] is True
    assert {s["name"] for s in result["skills"]} == {"oc"}


def test_list_skills_unknown_agent_unsupported(home: Path):
    assert skills_ops.list_skills("amp") == {"skills": [], "supported": False}


# ---------------------------------------------------------------------------
# get_skill
# ---------------------------------------------------------------------------


def test_get_skill_returns_content_and_supporting_files(home: Path):
    skill = home / ".claude" / "skills" / "docs"
    _write_skill(skill, "docs", "a documented skill", body="# Docs\nUse me.")
    (skill / "reference.md").write_text("ref\n", encoding="utf-8")
    (skill / "scripts").mkdir()
    (skill / "scripts" / "run.py").write_text("print(1)\n", encoding="utf-8")

    result = skills_ops.get_skill("claude", "docs")
    assert "Use me." in result["content"]
    file_paths = {f["path"] for f in result["files"]}
    assert file_paths == {"reference.md", "scripts/run.py"}  # SKILL.md excluded
    assert result["scope"] == "user"


def test_get_skill_not_found_and_traversal(home: Path):
    assert skills_ops.get_skill("claude", "nope") == {"error": "not_found"}
    assert skills_ops.get_skill("claude", "../etc") == {"error": "invalid_skill_name"}


def test_get_skill_follows_a_symlinked_skill(home: Path, tmp_path: Path):
    """A skill symlinked into the root from a repo (its real dir lives OUTSIDE
    the skills root) must still open — the confinement is on the link's parent,
    not the resolved target."""
    source = tmp_path / "repo" / "app-release-notes"
    _write_skill(source, "app-release-notes", "Release notes", body="# Notes")
    root = home / ".claude" / "skills"
    root.mkdir(parents=True)
    (root / "app-release-notes").symlink_to(source)

    result = skills_ops.get_skill("claude", "app-release-notes")
    assert "Notes" in result["content"]
    assert result.get("error") is None


def test_uninstall_symlinked_skill_removes_link_not_source(home: Path, tmp_path: Path):
    source = tmp_path / "repo" / "linked"
    _write_skill(source, "linked", "Linked skill")
    root = home / ".claude" / "skills"
    root.mkdir(parents=True)
    (root / "linked").symlink_to(source)

    assert skills_ops.uninstall_skill("claude", "linked") == {"ok": True}
    assert not (root / "linked").exists()  # the link is gone
    assert (source / "SKILL.md").is_file()  # the source repo is untouched


# ---------------------------------------------------------------------------
# install_skill
# ---------------------------------------------------------------------------


def test_install_skill_from_git_copies_tree_and_records_provenance(
    home: Path, tmp_path: Path
):
    repo = _make_skill_repo(
        tmp_path, name="gitskill", extra={"scripts/helper.py": "x=1\n"}
    )
    result = skills_ops.install_skill("claude", f"file://{repo}")

    assert result["name"] == "gitskill"
    assert result["source"].startswith("file://")
    dest = Path(result["path"])
    assert (dest / "SKILL.md").is_file()
    assert (dest / "scripts" / "helper.py").is_file()
    assert not (dest / ".git").exists()  # VCS metadata is never copied

    manifest = json.loads(
        (home / ".claude" / "skills" / ".vicoa-skills.json").read_text()
    )
    assert manifest["gitskill"]["source_url"].startswith("file://")
    assert manifest["gitskill"]["installed_at"]


def test_installed_skill_shows_source_and_manifest_is_not_scanned(
    home: Path, tmp_path: Path
):
    repo = _make_skill_repo(tmp_path, name="withsrc")
    skills_ops.install_skill("claude", f"file://{repo}")
    names = {s["name"]: s for s in skills_ops.list_skills("claude")["skills"]}
    assert ".vicoa-skills" not in names  # hidden manifest never surfaces as a skill
    assert names["withsrc"]["source"].startswith("file://")


def test_install_into_subdir_of_repo(home: Path, tmp_path: Path):
    repo = tmp_path / "monorepo"
    _write_skill(repo / "skills" / "nested", "nested", "in a subdir")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "x"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, env=env)
    result = skills_ops.install_skill(
        "claude", f"file://{repo}", subdir="skills/nested"
    )
    assert result["name"] == "nested"
    assert (home / ".claude" / "skills" / "nested" / "SKILL.md").is_file()


def test_install_duplicate_requires_overwrite(home: Path, tmp_path: Path):
    repo = _make_skill_repo(tmp_path, name="dup")
    assert skills_ops.install_skill("claude", f"file://{repo}")["name"] == "dup"
    assert skills_ops.install_skill("claude", f"file://{repo}") == {
        "error": "skill_exists"
    }
    assert (
        skills_ops.install_skill("claude", f"file://{repo}", overwrite=True)["name"]
        == "dup"
    )


def test_install_rejects_bad_url_and_unsupported_agent(home: Path):
    assert skills_ops.install_skill("claude", "not-a-url") == {"error": "invalid_url"}
    assert skills_ops.install_skill("amp", "https://x/y.git") == {
        "error": "unsupported_agent"
    }


def test_install_codex_lands_in_agents_shared(home: Path, tmp_path: Path):
    repo = _make_skill_repo(tmp_path, name="cx")
    result = skills_ops.install_skill("codex", f"file://{repo}")
    assert result["scope"] == "shared"
    assert (home / ".agents" / "skills" / "cx" / "SKILL.md").is_file()
    # Codex install is shared, so OpenCode (which also reads ~/.agents/skills) sees it.
    assert "cx" in {s["name"] for s in skills_ops.list_skills("opencode")["skills"]}


def test_install_rejects_escaping_subdir(home: Path, tmp_path: Path):
    repo = _make_skill_repo(tmp_path, name="ok")
    assert skills_ops.install_skill("claude", f"file://{repo}", subdir="../etc") == {
        "error": "invalid_subdir"
    }


def test_install_missing_skill_md(home: Path, tmp_path: Path):
    repo = tmp_path / "emptyrepo"
    repo.mkdir()
    (repo / "README.md").write_text("no skill here\n")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "x"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, env=env)
    assert skills_ops.install_skill("claude", f"file://{repo}") == {
        "error": "skill_md_not_found"
    }


def test_install_oversized_file_is_rejected(home: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(skills_ops, "_MAX_FILE_BYTES", 16)
    repo = _make_skill_repo(tmp_path, name="big", extra={"data.bin": "x" * 100})
    assert skills_ops.install_skill("claude", f"file://{repo}") == {
        "error": "file_too_large"
    }


# ---------------------------------------------------------------------------
# uninstall_skill
# ---------------------------------------------------------------------------


def test_uninstall_removes_dir_and_manifest_entry(home: Path, tmp_path: Path):
    repo = _make_skill_repo(tmp_path, name="gone")
    dest = Path(skills_ops.install_skill("claude", f"file://{repo}")["path"])
    assert dest.exists()

    assert skills_ops.uninstall_skill("claude", "gone") == {"ok": True}
    assert not dest.exists()
    manifest = json.loads(
        (home / ".claude" / "skills" / ".vicoa-skills.json").read_text()
    )
    assert "gone" not in manifest
    assert skills_ops.uninstall_skill("claude", "gone") == {"error": "not_found"}


def test_uninstall_rejects_path_traversal(home: Path):
    assert skills_ops.uninstall_skill("claude", "../evil") == {
        "error": "invalid_skill_name"
    }
    assert skills_ops.uninstall_skill("claude", "..") == {"error": "invalid_skill_name"}
