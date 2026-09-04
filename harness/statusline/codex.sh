#!/usr/bin/env bash
# Codex status line, as a reconciler rather than a renderer.
#
# The sibling claude.sh is a script Claude Code runs on every draw. Codex draws
# its own status line and cannot run a script at all: `[tui] status_line` takes
# an ordered list of built-in item ids, so what ports across is the content, not
# the code. This file is what writes those ids.
#
# Usage: codex.sh [--remove] [config.toml]
#
# Prints the reconciled file on stdout and exits 0 when something changed; exits
# 3 when the config already says this, having written nothing. The caller owns
# the write, so harness/install.sh can take its backup only on a real change
# rather than minting a fresh backup root on every run.
#
# --remove is what harness/install.sh --uninstall runs, and it is this same pass with the re-insert dropped: the loop below already deletes both managed keys before putting them back, so removal is that loop stopping early. An emptied [tui] header is left where it is, because Codex writes its own keys into that table and a harness that removes it would take them with it.
#
# 3 rather than the catch-all 1, matching clients/codex.sh beside it: a crash
# exits 1 too, and a caller that reads 1 as "nothing to do" leaves the status
# line unwritten while the run reports success.
#
# OpenCode has no third file here. Its configuration schema carries no status
# line field and @opencode-ai/plugin exposes no hook for one, so there is
# nothing to reconcile.

set -euo pipefail

# The closest match to the Claude line: model, context, directory, branch,
# reasoning effort, and the two rate-limit fields. `model` and `reasoning` are
# separate items rather than the combined `model-with-reasoning`, so effort sits
# after the branch the way it does in claude.sh. `project-name` falls back to
# the directory name, which is the basename claude.sh prints; `current-dir`
# would print the whole path. Session duration is dropped: Codex has no item
# for it.
ITEMS=(
    model
    context-used
    project-name
    git-branch
    reasoning
    five-hour-limit
    weekly-limit
)

remove=false
if [[ "${1-}" == --remove ]]; then
    remove=true
    shift
fi
config="${1:-$HOME/.codex/config.toml}"

# config.toml is hand-maintained and full of trust decisions and hook hashes, so
# this rewrites the two managed keys in place and leaves every other line byte
# for byte. Idempotence is textual rather than parsed: the reconciled file is a
# fixed point, so an unchanged run exits 3. That also avoids tomllib, which
# needs Python 3.11 and is therefore not on the system python3 macOS ships.
exec python3 - "$config" "$remove" "${ITEMS[@]}" <<'PY'
import pathlib, re, sys

path = pathlib.Path(sys.argv[1])
remove = sys.argv[2] == "true"
items = ", ".join(f'"{item}"' for item in sys.argv[3:])
managed = [f"status_line = [{items}]", "status_line_use_colors = true"]
current = path.read_text() if path.exists() else ""
# Nothing to remove from a config that is not there. Without this the
# reconciled text is a bare newline against an empty `current`, so removal
# reports a change and the caller creates ~/.codex/config.toml on a machine
# that had none.
if remove and not current.strip():
    raise SystemExit(3)
lines = current.splitlines()

kept, index, in_tui = [], 0, False
while index < len(lines):
    line = lines[index]
    stripped = line.strip()
    if stripped.startswith("["):
        in_tui = stripped == "[tui]"
    key = re.match(r"\s*(status_line|status_line_use_colors)\s*=\s*(.*)$", line)
    if in_tui and key:
        # An array the previous writer wrapped across lines is dropped whole.
        value = key.group(2)
        while value.count("[") > value.count("]") and index + 1 < len(lines):
            index += 1
            value += lines[index]
        index += 1
        continue
    kept.append(line)
    index += 1

headers = [line.strip() for line in kept]
if not remove:
    if "[tui]" in headers:
        at = headers.index("[tui]") + 1
        kept[at:at] = managed
    else:
        # Declaring [tui] after an existing [tui.*] subtable is valid TOML, so
        # appending is safe even on a config that already configures one.
        while kept and not kept[-1].strip():
            kept.pop()
        kept += ["", "[tui]", *managed]

text = "\n".join(kept).strip("\n") + "\n"
if text == current:
    raise SystemExit(3)
sys.stdout.write(text)
PY
