"""Isolation every test in this repo needs from the machine running it.

`effective_acp_agents()` reads `~/.vicoa/config.json` on purpose — that is how
a user adds an agent without waiting for a release — which quietly made the
agent-detection tests depend on whatever providers the developer happens to
have configured. They pass in CI, where no such file exists, and fail the
moment someone actually uses the feature on their own machine (found exactly
that way: adding CodeWhale from Settings → Providers turned two daemon tests
red).

Lives at the rootdir so it covers all four `testpaths`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_user_config(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point `~/.vicoa/config.json` at an empty per-test file.

    Returned so a test that wants to exercise config parsing can just write to
    it rather than repeat the patching.

    Deliberately NOT under the `tmp_path` fixture: this runs for every test,
    and a stray directory there is visible to anything that lists `tmp_path`
    (it broke the file-listing RPC tests when it was).
    """
    path = tmp_path_factory.mktemp("vicoa-home") / "config.json"

    import vicoa.cli as cli

    # Every reader resolves this lazily (`from vicoa.cli import …` inside the
    # function), so patching the attribute is enough.
    monkeypatch.setattr(cli, "get_user_config_path", lambda: path)

    # The effective spec table is cached per process, keyed on the config's
    # mtime — drop it so neither the real file nor another test's writes leak
    # in. Only when the module is already loaded: importing it here would pull
    # the whole ACP wrapper into every unrelated test.
    generic_acp = sys.modules.get("integrations.headless.generic_acp")
    if generic_acp is not None:
        monkeypatch.setattr(generic_acp, "_EFFECTIVE_CACHE", None)
        monkeypatch.setattr(generic_acp, "_EFFECTIVE_CACHE_STAMP", None)

    return path
