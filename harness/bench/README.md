# bench

`measure.py` answers one question: did a change to `harness/` move cost and friction in the sessions it actually produced?

The harness is prose, so re-reading a change and judging it plausible proves nothing. `POLICY.md` makes this the oracle for a harness change: compare the session population before and after the change's commit date. Cost and friction are what this measures. Quality stays a human read of the transcripts, and no number here substitutes for it.

## Usage

```sh
python3 harness/bench/measure.py --split <commit-date> --since <window-start>
```

| Flag | Meaning |
| --- | --- |
| `--split` | Required. The commit date of the harness change under test, `YYYY-MM-DD`. Sessions before it are the `before` cohort; sessions on or after it are `after`. |
| `--since` | Ignore sessions older than this date. Use it to cut off a period whose harness bears no resemblance to today's. |
| `--client` | Limit to `claude`, `codex`, or `opencode`. Repeatable. Defaults to all three. |
| `--home` | Session-store root. Defaults to the current home, and exists so the tests can point it at a fixture. |

## Metrics

Four per session, each a median across the cohort:

| Metric | What it counts |
| --- | --- |
| `turns` | Human turns. A tool result is the harness answering itself and never counts. |
| `tool_calls` | Tool invocations the assistant made. |
| `interrupts` | Times a human stopped a run in progress. |
| `denials` | Times a human refused a tool call. |

## Where the sessions come from

The harness is portable, so each client is read from its own store, in its own format.

- **Claude Code**, `~/.claude/projects/<slug>/*.jsonl`. Turns are `user` entries carrying no `tool_result` block; tool calls are `tool_use` blocks in `assistant` entries. Interrupts and denials are counted by matching the literal strings Claude Code writes into the transcript, `CLAUDE_INTERRUPT` and `CLAUDE_DENIAL` in `measure.py`. This is the only client that records all four metrics.
- **Codex**, `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. Turns are `response_item` messages with role `user`; tool calls are the payload types in `CODEX_TOOL_CALLS`, currently `function_call` and `custom_tool_call`; interrupts are `turn_aborted` events with reason `interrupted`. Codex does not record a declined tool call distinguishably, so `denials` is absent.
- **OpenCode**, `~/.local/share/opencode/opencode.db`. One SQL query over the `session`, `message`, and `part` tables. The database is opened read-only and immutable, because it may belong to a running client. OpenCode records neither interrupts nor denials durably, so both are absent.

A malformed JSONL line is skipped rather than fatal, and a file with no parseable timestamp yields no session at all: a store half-written by a live client should not take the report down.

## Reading the output

```
split 2026-09-02  since 2026-08-01

claude
  metric          before     after     delta
  sessions            34        29
  turns             12.0      9.0      -3.0
  tool_calls        41.0     38.0      -3.0
  interrupts         1.0      0.0      -1.0
  denials            0.0      0.0      +0.0
```

Two rules matter more than the numbers:

- **A metric a client does not record prints `-`, never `0`.** An absent measurement and a measured zero are different claims, and collapsing them would invent evidence. A `-` in the delta column means one side of the comparison was absent.
- **`THIN = 20`.** When either cohort holds fewer than 20 sessions, the report says so: `warning: a cohort has fewer than N sessions; noise, not a result.` Below that, a difference in medians is not a finding. Widen the window with `--since` or wait for more sessions.

Compare populations, not pairs. A single session before and a single session after prove nothing, whatever the delta says.
