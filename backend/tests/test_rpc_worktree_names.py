"""Worktree name generation — two-word slugs with per-repo uniqueness.

`worktree_names` owns the vocabulary and collision retry so the app stays
vocabulary-free and there is a single source of truth for what is taken.
"""

from __future__ import annotations

import random
import re
import subprocess
from pathlib import Path


def test_generated_name_is_two_lowercase_words_hyphenated(tmp_path: Path):
    from vicoa.rpc import worktree_names

    name = worktree_names.generate_unique_name(tmp_path, rng=random.Random(0))

    assert re.fullmatch(r"[a-z]+-[a-z]+", name), name


def test_taken_names_are_skipped_not_suffixed(tmp_path: Path):
    """A collision picks another free combination; no `-2` while any is left."""
    from vicoa.rpc import worktree_names

    first = worktree_names.generate_unique_name(tmp_path, rng=random.Random(0))
    (tmp_path / first).mkdir()
    branch_taken = worktree_names.generate_unique_name(tmp_path, rng=random.Random(1))

    name = worktree_names.generate_unique_name(
        tmp_path, is_taken=lambda n: n == branch_taken, rng=random.Random(1)
    )

    assert name not in (first, branch_taken)
    assert re.fullmatch(r"[a-z]+-[a-z]+", name), name


def test_the_last_free_combination_is_found(tmp_path: Path, monkeypatch):
    from vicoa.rpc import worktree_names

    monkeypatch.setattr(worktree_names, "ADJECTIVES", ["calm", "keen"])
    monkeypatch.setattr(worktree_names, "NOUNS", ["river", "ridge"])
    for taken in ("calm-river", "calm-ridge", "keen-river"):
        (tmp_path / taken).mkdir()

    for seed in range(5):
        assert (
            worktree_names.generate_unique_name(tmp_path, rng=random.Random(seed))
            == "keen-ridge"
        )


def test_suffix_only_once_every_combination_is_taken(tmp_path: Path, monkeypatch):
    from vicoa.rpc import worktree_names

    monkeypatch.setattr(worktree_names, "ADJECTIVES", ["calm"])
    monkeypatch.setattr(worktree_names, "NOUNS", ["river"])
    (tmp_path / "calm-river").mkdir()

    assert worktree_names.generate_unique_name(tmp_path) == "calm-river-2"
    assert (
        worktree_names.generate_unique_name(
            tmp_path, is_taken=lambda n: n == "calm-river-2"
        )
        == "calm-river-3"
    )


def test_vocabulary_is_large_unique_and_plain():
    from vicoa.rpc import worktree_names

    for words in (worktree_names.ADJECTIVES, worktree_names.NOUNS):
        assert len(words) >= 60
        assert len(set(words)) == len(words)
        assert all(re.fullmatch(r"[a-z]{3,8}", w) for w in words), words


def test_disambiguate_keeps_a_free_base_and_suffixes_a_taken_one(tmp_path: Path):
    from vicoa.rpc import worktree_names

    assert worktree_names.disambiguate(tmp_path, "feat-login") == "feat-login"

    (tmp_path / "feat-login").mkdir()
    assert worktree_names.disambiguate(tmp_path, "feat-login") == "feat-login-2"

    # A branch-only collision on the suffix skips to the next free one.
    assert (
        worktree_names.disambiguate(
            tmp_path, "feat-login", is_taken=lambda n: n == "feat-login-2"
        )
        == "feat-login-3"
    )


def test_every_vocab_combination_is_a_valid_git_ref():
    from vicoa.rpc import worktree_names

    # Sample a slug from each end of the vocabulary; git must accept the ref.
    for adj in (worktree_names.ADJECTIVES[0], worktree_names.ADJECTIVES[-1]):
        for noun in (worktree_names.NOUNS[0], worktree_names.NOUNS[-1]):
            slug = f"{adj}-{noun}"
            proc = subprocess.run(
                ["git", "check-ref-format", "--branch", slug],
                capture_output=True,
                check=False,
            )
            assert proc.returncode == 0, slug
