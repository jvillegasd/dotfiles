# bench

`measure.py` answers one question: did a change to `harness/` move cost and friction in the sessions it actually produced? `POLICY.md` makes this the oracle for a harness change, because re-reading prose and judging it plausible proves nothing. Quality stays a human read of the transcripts.

Deliberately not a synthetic task battery. https://github.com/sjdonado/dotfiles/tree/master/bench built one and deleted it after a day: its control tasks swung 4x between identical runs, and the tasks contaminated their own fixture. Real sessions cost something else, arriving slowly and mixing variables no experiment controls, which is what `THIN` and the caveats below are for.

## Usage

```sh
python3 harness/bench/measure.py --split <commit-date> --since <window-start>
```

| Flag | Meaning |
| --- | --- |
| `--split` | Required. Commit date of the change under test, `YYYY-MM-DD`. Sessions before it are `before`, on or after it `after`. |
| `--since` | Ignore sessions older than this. Cuts off a period whose harness bears no resemblance to today's. |
| `--client` | Limit to `claude`, `codex`, or `opencode`. Repeatable. |
| `--home` | Session-store root. Defaults to the current home; the tests point it at a fixture. |
| `--rows` | One JSON object per session instead of the report, honouring `--since`, for the distribution behind a median. |

## Metrics

Eight per session, each a median across the cohort. The first three are cost, the last three friction, the middle two what the harness claims to move.

| Metric | What it counts |
| --- | --- |
| `turns` | Human turns. A tool result, either shape of slash-command entry, a `<task-notification>`, local-command stdout, an `isMeta` caveat, an injected `<system-reminder>` and an interrupt marker are all the client writing to its own transcript, and none is a turn. |
| `tool_calls` | Tool invocations the assistant made. |
| `minutes` | First stamped entry to last. |
| `commands` | Slash-command invocations, so routing adoption is visible: `POLICY.md` is mostly a routing table. |
| `delegation` | Messages the session's subagents produced. `POLICY.md` names subagent overspawn as a failure mode. |
| `interrupts` | Times a human stopped a run. |
| `denials` | Times a human refused a tool call. |
| `errors` | Tool results that failed. A refusal is a denial, never also an error. |

## Cohorts

A hard week at work moves every metric without the harness changing. Copy `cohorts.example.json` to `cohorts.json` and name the projects that mean work:

```json
{ "work": ["acme", "some-client-repo"] }
```

Case-insensitive substrings, anything unmatched is personal, and the report splits only once a pattern matches something. `cohorts.json` is gitignored, since naming a client is the whole job of it.

Each client records a project differently: a dashed slug, a `cwd`, a `directory` column. Pattern and project are both folded by running every `-` and `/` into one separator, so one `acme` reaches all three. Name a path segment, not a span across one.

## Where the sessions come from

- **Claude Code**, `~/.claude/projects/<slug>/<session>.jsonl`. The only client recording all eight metrics. Interrupts and denials come from matching `CLAUDE_INTERRUPT` and `CLAUDE_DENIALS` in `measure.py`.
- **Codex**, `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`. Records no declined call, slash command, subagent, or distinguishable failed result, so those four are absent.
- **OpenCode**, `~/.local/share/opencode/opencode.db`, opened read-only and immutable because a client may be running. No interrupt, denial, failed result, or slash command, so those four are absent.

**A subagent is delegation, not a session.** Claude Code writes `<session-id>/subagents/*.jsonl` beside the session file, and OpenCode gives a subagent a `session` row carrying the parent's id, so a recursive glob or an unfiltered query counts them as sessions: on this machine, 273 sidecars against 209 real sessions, and 77 against 36. Both are excluded and counted as the parent's `delegation`. The inline `isSidechain` flag those entries used to carry is still written and now always false, so a reader still looking there reports no delegation rather than reporting it cannot see any.

## Reading the output

```
split 2026-09-02  since 2026-08-01

claude  work
  metric          before     after     delta
  sessions            34        29
  turns              4.0       3.0      -1.0
  tool_calls        41.0      38.0      -3.0
  minutes            9.4       7.1      -2.3
  commands           1.0       2.0      +1.0
  delegation         0.0      12.0     +12.0
  interrupts         1.0       0.0      -1.0
  denials            0.0       0.0      +0.0
  errors             2.0       2.0      +0.0
```

Headings are bare client names until a work pattern matches a session in the window. Two rules matter more than the numbers:

- **A metric a client does not record prints `-`, never `0`.** An absent measurement and a measured zero are different claims, and collapsing them would invent evidence.
- **`THIN = 20`.** Below that the report warns, and a difference in medians is not a finding.

Populations, not pairs, and require a real gap rather than a nudge: a `--split` compares two populations that differ in more than the split.

## Sharing

`measure.py` writes no files. The aggregate report names nothing and is fine to paste anywhere. `--rows` is not: each row carries the project the session ran in, which on a work machine is a client or an employer. `cohorts.json` is gitignored for the same reason.
