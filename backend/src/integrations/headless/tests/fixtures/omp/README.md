# OMP (`oh-my-pi`) RPC wire traces

Real frames captured from `omp --mode rpc`, one JSONL file per scenario, one
frame per line, verbatim except for the sanitization noted below. These are the
ground truth for the Pi/OMP wrapper's transport and event mapper — write the
parsers against these, not against a hand-written idea of the protocol.

Captured **2026-09-05** against:

| | |
|---|---|
| binary | `omp` 18.1.10 (`@oh-my-pi/pi-coding-agent`, needs Bun ≥ 1.3.14) |
| model | `claude-haiku-4-5-20251001` (via `--model haiku`) |
| flags | `--mode rpc --no-session --model haiku` (+ per-scenario extras) |

Regenerate with `capture.py` in this directory (see "Reproducing" below).

## Scenarios

| file | what it exercises | notable frames |
|---|---|---|
| `01-text.jsonl` | plain text turn, no tools | full `thinking_*` → `text_*` delta sequence, `turn_end` |
| `02-tools.jsonl` | native `read` tool | `tool_execution_start` / `_end` |
| `03-hosttool.jsonl` | full host-tool round trip | `host_tool_call`, our `host_tool_update` / `host_tool_result` reflected back |
| `04-approval.jsonl` | `--approval-mode always-ask` | the real permission dialog |
| `05-todo.jsonl` | todo list creation | `todo_reminder` + the native `todo` tool call |
| `06-subagent.jsonl` | `set_subagent_subscription: "events"` | `subagent_lifecycle` ×2, `subagent_progress` ×31, `subagent_event` ×110 |

## Sanitization

Only `available_commands_update` frames were modified: the real ones carry the
operator's full private slash-command and skill list (76 commands, 31 of them
personal skills). They are replaced with a small synthetic set that preserves
the shape, including a `subcommands` entry. **Every other frame is verbatim.**
No credentials, tokens or home-directory paths appear in any file (the capture
ran in `/tmp`).

## What these traces proved

Seven places where the real 18.1.10 wire disagrees with paseo's schemas
(`packages/server/src/server/agent/providers/omp/rpc-types.ts`, pinned to a
16.3.9 floor). Paseo uses `z.discriminatedUnion`, so unmodelled event types fail
`safeParse` and are silently dropped:

1. **`turn_end`** is a real event carrying the terminal assistant message plus
   `usage`. Not in paseo's union at all.
2. **`tool_execution_start.intent`** — a human-readable label
   (`"Reading sample.txt"`, `"Listing Vicoa sessions with limit 5"`). Unmodelled,
   and better than anything we would synthesize from `args` for a tool-card
   header.
3. **`todo_reminder.attempt` / `.maxAttempts`** — unmodelled.
4. **`available_commands_update` commands carry `subcommands`** — unmodelled.
5. **`subagent_event.payload.event` includes `advisor_cost_changed` and
   `thinking_level_changed`** — event types absent from paseo's union entirely.
6. **`get_session_stats`** returns `sessionId`, `userMessages`,
   `assistantMessages`, `toolCalls`, `toolResults`, `totalMessages`,
   `premiumRequests` and `tokens.reasoning` beyond paseo's shape.
7. **`get_state.model`** carries `int`, `tps`, `thinking:{mode,efforts,supportsDisplay}`,
   `identity:{class,family,revision}`, `requiresGlyphTokenization`, `tokenizer`,
   `supportsComputerUse`, `compat:{…}`.

⇒ **Parse extra-allow. Never use a closed union for OMP event types** — dispatch
on `type` with an explicit default branch that logs and drops.

## Facts the traces settle

- **Delta order** is `thinking_start` → `thinking_delta`* → `thinking_end` →
  `text_start` → `text_delta`* → `text_end`, each wrapped in
  `message_update.assistantMessageEvent`. Thinking blocks also carry a
  `thinkingSignature` in the final message.
- **`turn_*` is per model round trip, `agent_*` is per user prompt.** A single
  tool-using prompt produces `agent_start` → (`turn_start`…`turn_end`) ×2 →
  `agent_end`. Do not treat `turn_end` as end-of-work.
- **The `prompt` ack can be `data: null`** — not always `{agentInvoked}`. Do not
  assume an object.
- **Host tools render as ordinary tools.** A `host_tool_call` also emits the
  normal `tool_execution_start` / `_update` / `_end` triple, and our
  `host_tool_update.partialResult` comes back as
  `tool_execution_update.partialResult`. No separate rendering path is needed —
  and streaming progress works for free.
- **`host_tool_call` uses two distinct ids**: `id` (correlation id; the one that
  must be echoed in `host_tool_result`) and `toolCallId` (the model's
  `toolu_…` id, which is what the `tool_execution_*` events key on).
- **Permission prompts arrive as `extension_ui_request` with `method: "select"`**,
  a multi-line free-text `title` holding the whole prompt, and
  `options: ["Approve", "Deny"]`. Maps onto `headless/permission.py`'s existing
  prompt + options rendering.
- **`extension_ui_request` also fires with `method: "setWidget"`** in plain
  `--mode rpc` (not just `rpc-ui`), at session start and end. Unknown methods
  must be ignored silently.
- **`subagent_event` is a firehose** — 110 frames for one trivial subagent, since
  it nests the child's entire event stream. Default
  `set_subagent_subscription` to `"progress"`, not `"events"`, and derive cards
  from `subagent_lifecycle` + `subagent_progress`.
- **`subagent_lifecycle.payload.id` is a human-readable name** (`"DelightedDinosaur"`),
  not a UUID, and `parentToolCallId` is what links a subagent to its Task card.

## Reproducing

Requires an authenticated `omp` on the machine (`omp` → `/login`). Costs a few
cents on haiku.

```bash
cd backend/src/integrations/headless/tests/fixtures/omp
python3 capture.py            # rewrites the *.jsonl files in place
```

Re-sanitize `available_commands_update` before committing anything regenerated.
