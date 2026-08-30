"""Tests for the `scan-commands` RPC and the multi-agent command/skill scanner."""

from pathlib import Path

import pytest

from integrations.cli_wrappers.claude_code.command_sync import (
    _extract_command_description,
    scan_agent_commands,
    scan_claude_commands,
    scan_codex_commands,
)
from vicoa.rpc import command_index


@pytest.fixture()
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


def _write_skill(root: Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nBody.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


def test_block_scalar_description_reads_the_following_lines():
    content = (
        "---\n"
        "name: caveman\n"
        "description: >\n"
        "  Ultra-compressed communication mode.\n"
        "  Cuts token usage.\n"
        "---\n"
        "# Caveman\n"
    )
    assert (
        _extract_command_description(content, "caveman")
        == "Ultra-compressed communication mode. Cuts token usage."
    )


def test_plain_description_still_wins_over_body():
    content = "---\ndescription: One liner\n---\n# Heading\n"
    assert _extract_command_description(content, "x") == "One liner"


def test_indented_description_key_is_not_a_top_level_match():
    content = (
        "---\nmetadata:\n  description: nested value\ndescription: real value\n---\n"
    )
    assert _extract_command_description(content, "x") == "real value"


# ---------------------------------------------------------------------------
# Scanners: kind tagging and per-agent sources
# ---------------------------------------------------------------------------


def test_claude_scan_tags_commands_and_skills(home: Path, tmp_path: Path):
    commands_dir = home / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "ship.md").write_text(
        "---\ndescription: Ship it\n---\n", encoding="utf-8"
    )
    _write_skill(home / ".claude" / "skills", "review", "Review things")

    project = tmp_path / "project"
    project.mkdir()
    scanned = scan_claude_commands(project_root=project)

    assert scanned["ship"] == {"description": "Ship it", "kind": "command"}
    assert scanned["review"] == {"description": "Review things", "kind": "skill"}


def test_scan_ignores_skill_md_nested_inside_a_skill(home: Path, tmp_path: Path):
    """Only a direct child of the skills root is a skill. A bundle's vendored
    ``node_modules`` / ``test`` fixtures carrying their own ``SKILL.md`` are
    supporting files, not installed skills, and must not be scanned."""
    skills_root = home / ".claude" / "skills"
    _write_skill(skills_root, "gstack", "The gstack bundle")
    for buried in ("node_modules/playwright/skills/cli", "test/fixtures/alpha"):
        deep = skills_root / "gstack" / buried
        deep.mkdir(parents=True)
        (deep / "SKILL.md").write_text(
            "---\nname: x\ndescription: vendored\n---\n", encoding="utf-8"
        )

    scanned = scan_claude_commands(project_root=tmp_path / "project")

    assert scanned["gstack"] == {"description": "The gstack bundle", "kind": "skill"}
    # Neither the leaf name nor the old ``:``-joined path leaks in.
    assert "cli" not in scanned
    assert "alpha" not in scanned
    assert not any(":" in name for name in scanned)


def test_codex_scan_reads_prompts_and_all_skill_dirs(home: Path, tmp_path: Path):
    prompts = home / ".codex" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "fix.md").write_text(
        "---\ndescription: Fix bug\n---\n", encoding="utf-8"
    )

    _write_skill(home / ".agents" / "skills", "deploy", "Deploy the app")
    _write_skill(home / ".codex" / "skills", "lint", "Lint code")

    project = tmp_path / "project"
    _write_skill(project / ".agents" / "skills", "deploy", "Repo-scoped deploy")

    scanned = scan_codex_commands(project_root=project)

    assert scanned["fix"] == {"description": "Fix bug", "kind": "command"}
    assert scanned["lint"]["kind"] == "skill"
    assert scanned["lint"]["insert"] == "$lint"
    # Repo-scoped skill overrides the global one of the same name.
    assert scanned["deploy"]["description"] == "Repo-scoped deploy"
    assert scanned["deploy"]["insert"] == "$deploy"


def test_codex_scan_skips_hidden_system_skills(home: Path):
    _write_skill(home / ".codex" / "skills" / ".system", "internal", "Hidden")
    assert scan_codex_commands() == {}


def test_agents_without_a_local_source_scan_empty(home: Path):
    assert scan_agent_commands("opencode") == {}
    assert scan_agent_commands("amp") == {}


# ---------------------------------------------------------------------------
# RPC handler
# ---------------------------------------------------------------------------


def test_scan_commands_returns_sorted_entries_with_hash(home: Path):
    _write_skill(home / ".agents" / "skills", "b-skill", "B")
    prompts = home / ".codex" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "a-prompt.md").write_text("Prompt A\n", encoding="utf-8")

    result = command_index.scan_commands("codex")

    assert [c["name"] for c in result["commands"]] == ["a-prompt", "b-skill"]
    assert result["command_count"] == 2
    assert result["hash"]
    assert result["scanned_at"] > 0


def test_scan_commands_known_hash_short_circuits(home: Path):
    _write_skill(home / ".claude" / "skills", "foo", "Foo")

    first = command_index.scan_commands("claude")
    second = command_index.scan_commands("claude", known_hash=first["hash"])

    assert second == {"unchanged": True, "hash": first["hash"]}


def test_scan_commands_missing_cwd_still_scans_globals(home: Path):
    _write_skill(home / ".agents" / "skills", "foo", "Foo")

    result = command_index.scan_commands("codex", cwd="/does/not/exist")

    assert result["command_count"] == 1


def test_scan_commands_rejects_bad_agent_type(home: Path):
    assert command_index.scan_commands("") == {"error": "invalid_agent_type"}


# ---------------------------------------------------------------------------
# Wiring: the daemon must route and advertise the method
# ---------------------------------------------------------------------------


def test_daemon_advertises_scan_commands_and_the_command_index_capability():
    from vicoa.machine_daemon import MachineDaemon

    daemon = MachineDaemon.__new__(MachineDaemon)
    assert "scan-commands" in daemon._supported_rpc_methods()
    assert "command-index" in daemon._capabilities()


def test_daemon_dispatches_scan_commands_to_the_handler(home: Path):
    from vicoa.machine_daemon import MachineDaemon

    _write_skill(home / ".claude" / "skills", "foo", "Foo")

    daemon = MachineDaemon.__new__(MachineDaemon)
    result = daemon._handle_rpc_request(
        {"method": "scan-commands", "params": {"agent_type": "claude"}}
    )

    assert result["commands"][0]["name"] == "foo"
    assert result["commands"][0]["kind"] == "skill"
