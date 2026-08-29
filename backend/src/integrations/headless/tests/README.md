# Headless Claude runner tests

These tests cover `integrations.headless.claude_code.HeadlessClaudeRunner` and
its sibling modules:

- `integrations.headless.auq` — AskUserQuestion wire format and the
  Future-based `AskUserQuestionRegistry`.
- `integrations.headless.permission` — permission cache and prompt rendering.
- `integrations.headless.control_command` — control-command JSON parser.

## Layout

- `conftest.py` — shared fixtures (event-loop friendly, builds a half-init'd
  runner with `_permission_cache`, `_auq_registry`, and `_send_lock` wired up
  so the layer-2 handlers run unmodified).
- `_fakes.py` — `FakeAsyncVicoaClient`. Prefix is `_` so pytest does **not**
  collect it as a test module. Supports both the legacy
  `send_message_handler` (polling path, still used by permission tests) and
  `auq_reply` (Future-based path: schedules the reply through
  `runner._handle_control_command(...)` after the AUQ POST lands).
- `test_handlers_unit.py` — layer 1: pure-function unit tests for the
  runner's helpers (`_parse_control_command`, permission cache, prompt
  rendering, `_format_dict_as_markdown`).
- `test_auq_registry.py` — layer 1: unit tests for
  `auq.AskUserQuestionRegistry` (request_id / message_id / FIFO lookup
  priorities, resolve/cancel lifecycle).
- `test_format_tools.py` — layer 1: representative branches of
  `format_tool_use`.
- `test_runner_handlers.py` — layer 2: drive `_handle_tool_use`,
  `_handle_ask_user_question`, `_handle_permission_prompt`,
  `_maybe_route_ask_user_question_reply`, and `_handle_control_command`
  directly with `FakeAsyncVicoaClient` injected.

## Why this dir is **not** a Python package

There is no `__init__.py` on purpose. Two systems would otherwise ship the
tests to users:

1. `pyinstaller/vicoa.spec` calls `collect_submodules('integrations')`, which
   walks regular packages and does **not** descend into PEP 420 namespace
   directories.
2. `pyproject.toml`'s `[tool.setuptools.packages.find]` only finds regular
   packages (dirs with `__init__.py`).

Note: this dir is still importable from Python (`import
integrations.headless.tests`) because PEP 420 namespace packages don't need
`__init__.py`. That's fine — the wheel and PyInstaller bundle stay clean.

Belt-and-braces: `pyinstaller/vicoa.spec` also passes
`excludes=['integrations.headless.tests', 'integrations.headless.tests.*']`
to Analysis.

## Running

```bash
source .venv/bin/activate  # or `conda activate <your-env>`
pytest src/integrations/headless/tests
```
