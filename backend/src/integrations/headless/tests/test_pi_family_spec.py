"""Spec-table tests: capability rows, the Bun gate, and catalog alignment."""

from __future__ import annotations

import pytest

from integrations.headless.pi_family import spec as spec_mod
from integrations.headless.pi_family.spec import (
    PI_FAMILY_AGENTS,
    check_runtime_requirements,
    parse_version,
    resolve_agent_binary,
    version_at_least,
)
from protocol.agent_catalog import AGENT_CATALOG, PERMISSION_MODES


def test_the_table_holds_exactly_the_two_agents():
    assert set(PI_FAMILY_AGENTS) == {"pi", "omp"}


def test_capability_rows_match_what_the_clis_actually_implement():
    omp, pi = PI_FAMILY_AGENTS["omp"], PI_FAMILY_AGENTS["pi"]
    # Probed live: `set_host_tools` on pi 0.85.0 answers "Unknown command".
    assert omp.supports_host_tools and not pi.supports_host_tools
    assert omp.supports_subagents and not pi.supports_subagents
    # omp emits an unsolicited `ready`; pi answers requests straight away.
    assert omp.expects_ready_frame and not pi.expects_ready_frame
    assert omp.negotiate_protocol_version == 2
    assert pi.negotiate_protocol_version is None
    # The slash-command RPC is the one rename between them.
    assert omp.commands_rpc == "get_available_commands"
    assert pi.commands_rpc == "get_commands"
    # pi has no approval flag at all.
    assert omp.approval_mode_arg == "--approval-mode"
    assert pi.approval_mode_arg is None


def test_settle_signals_differ_and_are_both_declared():
    """pi emits a dedicated ``agent_settled``; omp stamps ``isTerminal`` on
    ``agent_end`` instead."""
    assert PI_FAMILY_AGENTS["pi"].settle_event == "agent_settled"
    assert PI_FAMILY_AGENTS["omp"].settle_event is None


def test_approval_modes_reuse_vicoas_shared_permission_slugs():
    """Minting ask/write/full would fork the clients' mode picker and the
    daemon's PERMISSION_MODES validation."""
    omp = PI_FAMILY_AGENTS["omp"]
    assert set(omp.approval_modes) == PERMISSION_MODES["omp"]
    assert set(omp.approval_modes.values()) == {"always-ask", "write", "yolo"}


def test_every_pi_family_agent_is_in_the_catalog():
    catalog_ids = {agent["id"] for agent in AGENT_CATALOG["agents"]}
    assert set(PI_FAMILY_AGENTS) <= catalog_ids


def test_catalog_thinking_efforts_are_a_subset_of_what_each_cli_accepts():
    """The catalog deliberately omits ``minimal``/``auto`` to avoid widening
    the shared enum — but nothing it does offer may be rejected at launch."""
    by_id = {agent["id"]: agent for agent in AGENT_CATALOG["agents"]}
    for agent_id, agent_spec in PI_FAMILY_AGENTS.items():
        offered = {e["id"] for e in by_id[agent_id].get("thinking_efforts") or []}
        assert offered <= set(agent_spec.thinking_levels)


def test_pi_offers_no_permission_modes_because_it_has_no_approval_flag():
    assert "pi" not in PERMISSION_MODES


@pytest.mark.parametrize(
    "text,expected",
    [
        ("omp/18.1.10", (18, 1, 10)),
        ("1.4.1", (1, 4, 1)),
        ("v0.85.0\n", (0, 85, 0)),
        ("no version here", None),
        (None, None),
    ],
)
def test_version_parsing_tolerates_each_clis_own_format(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    "actual,minimum,ok",
    [
        ("1.4.1", "1.3.14", True),
        ("1.3.14", "1.3.14", True),
        ("1.3.12", "1.3.14", False),
        ("1.3.2", "1.3.14", False),
        # An unparseable version fails OPEN: far more likely an upstream format
        # change than a genuinely old install.
        ("weird-build", "1.3.14", True),
        ("1.0.0", None, True),
    ],
)
def test_version_comparison(actual, minimum, ok):
    assert version_at_least(actual, minimum) is ok


def test_missing_binary_reports_the_install_hint():
    error = check_runtime_requirements(PI_FAMILY_AGENTS["pi"], which=lambda _n: None)
    assert error is not None
    assert "npm install -g @earendil-works/pi-coding-agent" in error


def test_omp_with_an_old_bun_is_refused_before_the_session_exists():
    """Without this the failure surfaces as an unexplained 'exited with code 1'
    after a session row has already been created."""
    error = check_runtime_requirements(
        PI_FAMILY_AGENTS["omp"],
        which=lambda name: f"/usr/local/bin/{name}",
        run_version=lambda _cmd: "1.3.12",
    )
    assert error is not None
    assert "1.3.14" in error and "1.3.12" in error


def test_omp_without_bun_at_all_says_so():
    error = check_runtime_requirements(
        PI_FAMILY_AGENTS["omp"],
        which=lambda name: None if name == "bun" else "/usr/local/bin/omp",
        run_version=lambda _cmd: None,
    )
    assert error is not None and "Bun" in error


def test_omp_with_a_new_enough_bun_passes():
    assert (
        check_runtime_requirements(
            PI_FAMILY_AGENTS["omp"],
            which=lambda name: f"/usr/local/bin/{name}",
            run_version=lambda _cmd: "1.4.1",
        )
        is None
    )


def test_pi_needs_no_bun_because_it_runs_on_node():
    assert PI_FAMILY_AGENTS["pi"].requires_bun is None
    assert (
        check_runtime_requirements(
            PI_FAMILY_AGENTS["pi"],
            which=lambda name: "/usr/local/bin/pi" if name == "pi" else None,
        )
        is None
    )


def test_binary_resolution_falls_back_to_extra_dirs(tmp_path, monkeypatch):
    binary = tmp_path / "omp"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setattr(spec_mod.shutil, "which", lambda _n: None)
    from dataclasses import replace

    spec = replace(PI_FAMILY_AGENTS["omp"], extra_dirs=(str(tmp_path),))
    assert resolve_agent_binary(spec) == str(binary)
