# scenarios

`runner.py` answers a different question than `bench/measure.py`. `measure.py` reports whether a harness change moved cost and friction across real sessions. It cannot see whether a workflow preserved its requirements or produced the intended artifacts. A scenario does: it declares the artifacts and assertions it expects up front, runs in a disposable repository, and retains every attempt for review.

## Usage

```sh
python3 harness/scenarios/runner.py validate
python3 harness/scenarios/runner.py run
python3 harness/scenarios/runner.py report
```

| Command | Effect |
| --- | --- |
| `validate` | Reject any declaration that names no artifacts or assertions, before a session runs. |
| `run` | Execute each scenario and write one attempt per run under `attempts/`. |
| `report` | Print `local-tooling` and `behavioral-acceptance` as separate lines. |

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
| `status.json` | The computed state and its reasons. |

## States

`evaluate` returns the first state that holds:

| State | Meaning |
| --- | --- |
| `incomplete` | A required evidence file is missing or unreadable. |
| `stale` | The scenario or a declared harness input changed since the attempt. |
| `fail` | An artifact check failed, including a blocked forge call. |
| `unreviewed` | Artifacts passed but no `review.json` record exists. |
| `pass` | Artifacts passed and the transcript has a review record. |

A transcript review is a `review.json` beside the attempt with `{"reviewed": true}`. It is the record that a human read the transcript, which artifact checks alone cannot supply.

`run` additionally reports `not-run` for a live scenario that has neither a recording nor `--allow-paid`. That is not an evaluated state: nothing ran, so no attempt is written.

## Isolation

Every scenario runs in a fresh temporary repository with no git remote. A `gh` shim is placed first on `PATH`; it logs each call and exits nonzero, so a scenario cannot reach a real forge or tracker. `GH_TOKEN` and `GITHUB_TOKEN` are cleared. Any logged call fails the attempt under `no-external-forge`.

## Paid execution

A `live` scenario needs a recording under `fixtures/<id>/` or `--allow-paid`. Paid execution additionally needs `--max-sessions`, which is retained in `attempts/batch.json` and refuses a session beyond the cap. Changing the cap mid-batch is refused; start a new batch.

## Fixtures

A fixture is a recorded attempt. Its `repo/` holds the files the recorded session produced, and those files are materialized into the disposable repository; its `events.jsonl` and `transcript.jsonl` become the attempt's evidence. An absent `repo/` means the session wrote nothing, which is exactly what `tree_unchanged: true` asserts for a read-only command. The shipped `ask-read-only` fixture exercises the read-only scenario offline. It is test data, not a claim about a specific session.
