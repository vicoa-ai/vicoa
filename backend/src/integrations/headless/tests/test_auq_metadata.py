"""Shape of the AskUserQuestion metadata the dashboard pickers parse."""

from __future__ import annotations

from integrations.headless.auq import build_metadata


def test_option_preview_reaches_the_picker() -> None:
    metadata = build_metadata(
        questions=[
            {
                "question": "Which X post should go out?",
                "header": "X post",
                "multiSelect": False,
                "options": [
                    {
                        "label": "Changelog",
                        "description": "Lists the fixes",
                        "preview": "Vicoa 1.9.13 is out:\n\n  - previews in the picker",
                    },
                    {
                        "label": "Story",
                        "description": "One user's day",
                        "preview": "  ",
                    },
                ],
            }
        ],
        prompt="",
        tool_use_id="toolu_1",
        request_id="req_1",
    )

    changelog, story = metadata["ask_user_question"]["questions"][0]["options"]
    # Kept verbatim: indentation is part of a mockup.
    assert changelog["preview"] == "Vicoa 1.9.13 is out:\n\n  - previews in the picker"
    assert "preview" not in story
