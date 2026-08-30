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


def test_directory_collision_appends_numeric_suffix(tmp_path: Path):
    from vicoa.rpc import worktree_names

    base = worktree_names._random_slug(random.Random(0))
    (tmp_path / base).mkdir()

    name = worktree_names.generate_unique_name(tmp_path, rng=random.Random(0))

    assert name == f"{base}-2"


def test_branch_collision_via_is_taken_predicate(tmp_path: Path):
    from vicoa.rpc import worktree_names

    base = worktree_names._random_slug(random.Random(0))

    name = worktree_names.generate_unique_name(
        tmp_path, is_taken=lambda n: n == base, rng=random.Random(0)
    )

    assert name == f"{base}-2"


def test_two_collisions_append_three(tmp_path: Path):
    from vicoa.rpc import worktree_names

    base = worktree_names._random_slug(random.Random(0))
    (tmp_path / base).mkdir()
    (tmp_path / f"{base}-2").mkdir()

    name = worktree_names.generate_unique_name(tmp_path, rng=random.Random(0))

    assert name == f"{base}-3"


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
