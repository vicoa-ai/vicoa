"""Two-word worktree/branch name generation.

Picks a friendly `adjective-noun` slug (a valid git ref) that is not already
taken — either as a directory under the repo's workspace dir or as an existing
branch — falling back to a numeric suffix only once every combination is used.
It is the fallback name: a spawn with a prompt is usually renamed from it before
launch (`worktree_auto_name`). The vocabulary lives here so the app never has
to know it; the daemon is the single source of truth for what is taken.

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
# Short, plain words that can't be mistaken for a real branch's purpose
# (no main/test/fix/release). 60 x 60 = 3,600 names per repo.
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
    "azure",
    "breezy",
    "bright",
    "brisk",
    "cheery",
    "cosmic",
    "cozy",
    "crisp",
    "dapper",
    "daring",
    "dreamy",
    "frosty",
    "glossy",
    "grand",
    "hardy",
    "humble",
    "kind",
    "lively",
    "lofty",
    "lunar",
    "merry",
    "misty",
    "noble",
    "plucky",
    "rosy",
    "rustic",
    "sandy",
    "sleek",
    "snowy",
    "solar",
    "sunny",
    "tender",
    "velvet",
    "wise",
    "woolly",
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
    "acorn",
    "aspen",
    "badger",
    "bamboo",
    "beacon",
    "birch",
    "bison",
    "brook",
    "cactus",
    "cove",
    "crane",
    "dune",
    "fern",
    "finch",
    "fjord",
    "grove",
    "heron",
    "island",
    "juniper",
    "kestrel",
    "lark",
    "lotus",
    "marsh",
    "mesa",
    "oasis",
    "owl",
    "panda",
    "prairie",
    "puffin",
    "raven",
    "reef",
    "robin",
    "spruce",
    "tulip",
    "walrus",
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

    Picks at random among the combinations that are still free (see
    `disambiguate` for what "taken" means), so a `-2` suffix only appears once
    every combination is in use; then a random base is suffixed. Removing a
    worktree keeps its branch, so its name stays taken: a new worktree never
    lands on an old one's path. `is_taken` is called for many candidates, so
    pass a cheap lookup, not a git call.
    """
    rng = rng or random.Random()
    taken = is_taken or (lambda _name: False)
    repo_dir = Path(workspaces_repo_dir)
    candidates = [f"{adj}-{noun}" for adj in ADJECTIVES for noun in NOUNS]
    rng.shuffle(candidates)
    for slug in candidates:
        if not taken(slug) and not (repo_dir / slug).exists():
            return slug
    return disambiguate(repo_dir, _random_slug(rng), is_taken=is_taken)
