#!/usr/bin/env bash
# The tracked top-level Codex settings, reconciled into ~/.codex/config.toml.
#
# Usage: codex.sh [--remove] [config.toml] [tracked.toml]
#
# Same contract as statusline/codex.sh, which reconciles the [tui] half of the
# same file: prints the reconciled config on stdout and exits 0 when something
# changed, exits 3 when the config already says this, having written nothing,
# exits 2 naming the config it could not read, and exits 4 when the defect is
# in clients/codex.toml instead, because that one is a repository bug and
# naming the user's config for it sends them to the wrong file. The caller owns
# the write, so harness/install.sh takes its backup only on a real change.
#
# --remove is what harness/install.sh --uninstall runs. It is the same pass with the write-back dropped: the loop below already deletes every owned key before re-emitting it, so removal is that loop without the re-emit, and the tracked file is still read because it is what says which keys are owned. Exit 3 then means the config already carries none of them.
#
# "Already correct" is 3 rather than the catch-all 1 for the reason the Claude
# half carries the same three codes: a crash exits 1 too, and a caller reading
# that as "nothing to do" leaves the tracked keys unwritten while the run
# reports success. check_links re-runs this script to verify the write, so an
# overloaded 1 would have confirmed its own silence.

set -euo pipefail

remove=false
if [[ "${1-}" == --remove ]]; then
    remove=true
    shift
fi
config="${1:-$HOME/.codex/config.toml}"
tracked="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/codex.toml}"

# Textual rather than parsed, for the reason statusline/codex.sh gives: tomllib
# needs Python 3.11 and the system python3 macOS ships is older. Only the lines
# above the first table header are touched, because a key this file owns can
# also be a legitimate key inside somebody else's table.
#
# A line carrying a key this file owns is replaced whole, continuation lines of
# a wrapped value included, so a trailing comment on one is lost. Splitting it
# off would need to know where the value ends, and a `#` inside a quoted value
# would be mis-split into a comment, which corrupts the value rather than
# preserving a note about it. Put a note about an owned key on its own line
# above it, or in clients/codex.toml.
exec python3 - "$config" "$tracked" "$remove" <<'PY'
import pathlib, re, sys

config, tracked = (pathlib.Path(argument) for argument in sys.argv[1:3])
remove = sys.argv[3] == "true"


def read(path, status, missing_is_empty=False):
    try:
        return path.read_text()
    except FileNotFoundError:
        if missing_is_empty:
            return ""
        print(f"{path}: not found", file=sys.stderr)
        raise SystemExit(status)
    except (OSError, UnicodeDecodeError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        raise SystemExit(status)


KEY = re.compile(r"\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)$")


def wrapped(lines, index, value):
    """Index of the last line of a value the writer wrapped across lines.

    An array is the only top-level value that wraps, and taking just its first
    line is what turns `model = [` into a replaced line followed by an orphaned
    `"x"` and `]`. That is invalid TOML the reconciler then treats as a fixed
    point, so the install certifies a config Codex cannot load.
    """
    while value.count("[") > value.count("]") and index + 1 < len(lines):
        index += 1
        value += lines[index]
    return index


managed, tracked_lines = {}, read(tracked, 4).splitlines()
index = 0
while index < len(tracked_lines):
    key = KEY.match(tracked_lines[index])
    if key:
        last = wrapped(tracked_lines, index, key.group(2))
        managed[key.group(1)] = "\n".join(
            line.strip() for line in tracked_lines[index : last + 1]
        )
        index = last
    index += 1

current = read(config, 2, missing_is_empty=True)
# Nothing to remove from a config that is not there. Without this the
# reconciled text is a bare newline against an empty `current`, so removal
# reports a change and the caller creates ~/.codex/config.toml on a machine
# that had none.
if remove and not current.strip():
    raise SystemExit(3)
lines = current.splitlines()
head, tail, written = [], [], set()
index = 0
while index < len(lines):
    line = lines[index]
    if tail or line.lstrip().startswith("["):
        tail.append(line)
        index += 1
        continue
    key = KEY.match(line)
    if key and key.group(1) in managed:
        # A wrapped value is replaced whole, and a repeated key is invalid
        # TOML, so a duplicate is dropped rather than reconciled twice.
        index = wrapped(lines, index, key.group(2))
        if key.group(1) not in written and not remove:
            written.add(key.group(1))
            head.append(managed[key.group(1)])
        index += 1
        continue
    head.append(line)
    index += 1

# A missing key goes after the last top-level line, and whatever blank lines
# separated that block from the first table are put back in their own order.
# Rewriting the separator instead is what cost this reconciler its fixed point:
# `engram setup` writes its own keys without one, so the two took turns adding
# and dropping a blank line and every run rewrote the file. Reversing matters
# for the same reason: a blank line and a whitespace-only line are different
# text, so popping without restoring the order swaps them on every run.
blanks = []
while head and not head[-1].strip():
    blanks.append(head.pop())
blanks.reverse()
if not remove:
    head += [line for key, line in managed.items() if key not in written]
head += blanks

text = "\n".join(head + tail).strip("\n") + "\n"
if text == current:
    raise SystemExit(3)
sys.stdout.write(text)
PY
