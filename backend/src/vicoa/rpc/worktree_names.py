"""Two-word worktree/branch name generation.

Picks a friendly `adjective-noun` slug (a valid git ref) and disambiguates
with a numeric suffix when the name is already taken — either as a directory
under the repo's workspace dir or as an existing branch. The vocabulary lives
here so the app never has to know it; the daemon is the single source of truth
for what is taken.

The same suffixing (`disambiguate`) also produces the free-name suggestion the
`git-worktree-check-name` RPC hands back when a user-typed name collides — so
a random name and a suggested one always look alike.
"""

from __future__ import annotations

import os
import random
from collections.abc import Callable
from pathlib import Path

# Kept lowercase + hyphen-free so `adjective-noun` is always a valid git ref.
ADJECTIVES = [
    "amber",
    "bold",
    "brave",
    "calm",
    "clever",
    "crimson",
    "eager",
    "fuzzy",
    "gentle",
    "golden",
    "happy",
    "jolly",
    "keen",
    "lucky",
    "mellow",
    "nimble",
    "polished",
    "quiet",
    "rapid",
    "silver",
    "swift",
    "teal",
    "vivid",
    "witty",
    "zesty",
]

NOUNS = [
    "river",
    "meadow",
    "harbor",
    "summit",
    "canyon",
    "falcon",
    "otter",
    "willow",
    "cedar",
    "comet",
    "ember",
    "garden",
    "glacier",
    "lagoon",
    "lantern",
    "maple",
    "orchard",
    "pebble",
    "quartz",
    "ridge",
    "sparrow",
    "thistle",
    "tundra",
    "valley",
    "wharf",
]


def _random_slug(rng: random.Random) -> str:
    return f"{rng.choice(ADJECTIVES)}-{rng.choice(NOUNS)}"


def disambiguate(
    workspaces_repo_dir: str | os.PathLike[str],
    base: str,
    *,
    is_taken: Callable[[str], bool] | None = None,
) -> str:
    """Return `base`, or the first `base-2`, `base-3`, … that is free.

    A name is taken if a directory of that name already exists under
    `workspaces_repo_dir` or `is_taken(name)` returns True (used by the caller
    to reject names that collide with an existing branch).
    """
    taken = is_taken or (lambda _name: False)
    repo_dir = Path(workspaces_repo_dir)

    candidate = base
    suffix = 2
    while (repo_dir / candidate).exists() or taken(candidate):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def generate_unique_name(
    workspaces_repo_dir: str | os.PathLike[str],
    *,
    is_taken: Callable[[str], bool] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Return a unique `adjective-noun` slug for a new worktree.

    Collisions (see `disambiguate`) append `-2`, `-3`, … to the base slug
    until a free name is found.
    """
    rng = rng or random.Random()
    return disambiguate(workspaces_repo_dir, _random_slug(rng), is_taken=is_taken)
