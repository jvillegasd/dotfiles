# scenarios

`runner.py` answers a different question than `bench/measure.py`. `measure.py` reports whether a harness change moved cost and friction across real sessions. It cannot see whether a workflow preserved its requirements or produced the intended artifacts. A scenario does: it declares the artifacts and assertions it expects up front, runs in a disposable repository, and retains every attempt for review. `compare` then puts two retained batches side by side, correctness before cost.

## Usage

```sh
python3 harness/scenarios/runner.py validate
python3 harness/scenarios/runner.py run
python3 harness/scenarios/runner.py report
python3 harness/scenarios/runner.py compare --before <dir> --after <dir>
```

| Command | Effect |
| --- | --- |
| `validate` | Reject any declaration that names no artifacts or assertions, before a session runs. |
| `run` | Execute each scenario and write one attempt per run under `attempts/`. |
| `report` | Print `local-tooling` and `behavioral-acceptance` as separate lines. |
| `compare` | Report behavioral pass rates first, then efficiency among passing runs only. |

`--matrix`, `--out`, and `--root` override the declaration file, the attempts directory, and the repository root. `run --scenario <id>` narrows to one scenario.

## Attempts

Each attempt under `attempts/<id>/<stamp>-<digest>/` retains:

| File | Holds |
| --- | --- |
| `prompts.txt` | The declared prompt. |
| `provenance.json` | The input digest and the executor that produced the attempt. |
| `events.jsonl` | Tool and command events. |
| `artifacts.json` | One result per declared artifact or assertion. |
| `transcript.jsonl` | The recorded session or command output. |
| `metrics.json` | Normalized efficiency: tokens, tool calls, output bytes, wall time, model, terminal status. |
| `status.json` | The computed state and its reasons. |

## States

`evaluate` returns the first state that holds:

| State | Meaning |
| --- | --- |
| `incomplete` | A required evidence file is missing or unreadable. |
| `stale` | The scenario or a declared harness input changed since the attempt. |
| `interrupted` | The recorded run was killed by a signal rather than failing on its own. |
| `fail` | An artifact check failed, including a blocked forge call. |
| `unreviewed` | Artifacts passed but no `review.json` record exists. |
| `pass` | Artifacts passed and the transcript has a review record. |
| `unavailable` | No attempt exists for the scenario, so nothing ran in this batch. |

A transcript review is a `review.json` beside the attempt with `{"reviewed": true}`. It is the record that a human read the transcript, which artifact checks alone cannot supply.

`run` additionally reports `not-run` for a live scenario that has neither a recording nor `--allow-paid`. That is not an evaluated state: nothing ran, so no attempt is written.

## Metrics

Every attempt carries `metrics.json`, normalized from the recorded events so two runs of the same scenario and model are comparable:

| Field | Holds |
| --- | --- |
| `scenario`, `model` | What ran. `model` is `null` when the recording names none. |
| `input_tokens`, `output_tokens`, `cached_input` | Token usage, `null` when nobody measured it. |
| `tool_calls` | Tool invocations the run made. |
| `command_output_bytes` | Bytes the run's commands returned. |
| `wall_seconds` | First to last of the executor. |
| `terminal_status` | `ok`, `failed`, `interrupted`, or `unknown` when nothing was executed. |

An absent token count is `null`, never `0`: an unmeasured field and a measured zero are different claims, and collapsing them would invent evidence.

## Compare

`compare --before <dir> --after <dir>` puts two retained batches from different harness versions side by side. It reports behavioral pass rates first, counting every state so failed, interrupted, stale, unavailable, and unreviewed attempts stay visible. It then reports efficiency metrics among passing runs only, pairing one scenario and model at a time, so unlike models or scenarios are never pooled and a failed baseline can never read as an efficiency win. A comparison resting on a single successful pair prints `smoke`: one pair is a smoke result, not a savings claim.

## Isolation

Every scenario runs in a fresh temporary repository with no git remote. A `gh` shim is placed first on `PATH`; it logs each call and exits nonzero, so a scenario cannot reach a real forge or tracker. `GH_TOKEN` and `GITHUB_TOKEN` are cleared. Any logged call fails the attempt under `no-external-forge`.

## Paid execution

A `live` scenario needs a recording under `fixtures/<id>/` or `--allow-paid`. Paid execution additionally needs `--max-sessions`, which is retained in `attempts/batch.json` and refuses a session beyond the cap. Changing the cap mid-batch is refused; start a new batch.

## Fixtures

A fixture is a recorded attempt. Its `repo/` holds the files the recorded session produced, and those files are materialized into the disposable repository; its `events.jsonl` and `transcript.jsonl` become the attempt's evidence. An absent `repo/` means the session wrote nothing, which is exactly what `tree_unchanged: true` asserts for a read-only command. The shipped `ask-read-only` fixture exercises the read-only scenario offline. It is test data, not a claim about a specific session.
