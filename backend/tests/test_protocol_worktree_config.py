"""Worktree lifecycle config parser — normalization + shape.

The daemon (committed ``vicoa.json``) and the backend (project entity JSONB) both
funnel through these helpers, so the two substrates can never disagree on how a
``str | string[]`` hook value becomes a command list.
"""

from __future__ import annotations

from protocol.worktree_config import (
    WorktreeConfig,
    normalize_lifecycle_commands,
    parse_committed_config,
    parse_worktree_config,
)


class TestNormalizeLifecycleCommands:
    def test_string_becomes_single_element_list(self) -> None:
        assert normalize_lifecycle_commands("npm ci") == ["npm ci"]

    def test_blank_string_drops(self) -> None:
        assert normalize_lifecycle_commands("   ") == []
        assert normalize_lifecycle_commands("") == []

    def test_list_keeps_nonblank_strings_in_order(self) -> None:
        assert normalize_lifecycle_commands(["npm ci", "  ", "npm run build", ""]) == [
            "npm ci",
            "npm run build",
        ]

    def test_list_drops_non_strings(self) -> None:
        assert normalize_lifecycle_commands(["ok", 3, None, {"x": 1}]) == ["ok"]

    def test_non_string_non_list_is_empty(self) -> None:
        assert normalize_lifecycle_commands(None) == []
        assert normalize_lifecycle_commands({"setup": "x"}) == []
        assert normalize_lifecycle_commands(42) == []


class TestParseWorktreeConfig:
    def test_inner_object(self) -> None:
        config = parse_worktree_config(
            {"setup": "npm ci", "teardown": ["rm -rf node_modules"]}
        )
        assert config.setup == ["npm ci"]
        assert config.teardown == ["rm -rf node_modules"]

    def test_missing_keys_default_empty(self) -> None:
        config = parse_worktree_config({"setup": "npm ci"})
        assert config.setup == ["npm ci"]
        assert config.teardown == []

    def test_non_dict_is_empty(self) -> None:
        assert parse_worktree_config(None).is_empty()
        assert parse_worktree_config("nope").is_empty()

    def test_round_trip_to_dict(self) -> None:
        config = WorktreeConfig(setup=["a"], teardown=["b", "c"])
        assert config.to_dict() == {"setup": ["a"], "teardown": ["b", "c"]}
        assert parse_worktree_config(config.to_dict()) == config


class TestParseCommittedConfig:
    def test_file_wraps_hooks_under_worktree(self) -> None:
        config = parse_committed_config(
            {"worktree": {"setup": ["npm ci"], "teardown": "echo bye"}}
        )
        assert config.setup == ["npm ci"]
        assert config.teardown == ["echo bye"]

    def test_no_worktree_key_is_empty(self) -> None:
        assert parse_committed_config({"other": 1}).is_empty()

    def test_non_dict_is_empty(self) -> None:
        assert parse_committed_config(None).is_empty()
        assert parse_committed_config([1, 2, 3]).is_empty()
