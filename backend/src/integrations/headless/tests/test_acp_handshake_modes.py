"""``acp_handshake.session_modes`` leads with the agent's current mode: the
list is what gets cached per machine, and the clients read its first entry as
the agent's default."""

from __future__ import annotations

from integrations.headless.acp_handshake import current_mode_first, session_modes


def test_session_modes_puts_current_mode_first():
    result = {
        "modes": {
            "currentModeId": "plan",
            "availableModes": [
                {"id": "build", "name": "Build"},
                {"id": "plan", "name": "Plan"},
                {"id": "ask"},  # no name -> id as label
            ],
        }
    }
    assert session_modes(result) == [
        {"id": "plan", "label": "Plan"},
        {"id": "build", "label": "Build"},
        {"id": "ask", "label": "ask"},
    ]


def test_session_modes_keeps_order_without_a_known_current():
    modes = [{"id": "build", "name": "Build"}, {"id": "plan", "name": "Plan"}]
    assert session_modes({"modes": {"availableModes": modes}}) == [
        {"id": "build", "label": "Build"},
        {"id": "plan", "label": "Plan"},
    ]
    assert session_modes(
        {"modes": {"currentModeId": "nope", "availableModes": modes}}
    ) == [
        {"id": "build", "label": "Build"},
        {"id": "plan", "label": "Plan"},
    ]
    assert session_modes({}) == []
    assert session_modes({"modes": "junk"}) == []


def test_current_mode_first_is_stable_for_the_rest():
    entries = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
    assert current_mode_first(entries, "c") == [
        {"id": "c"},
        {"id": "a"},
        {"id": "b"},
        {"id": "d"},
    ]
    assert current_mode_first(entries, None) is entries
    assert current_mode_first(entries, "") is entries
