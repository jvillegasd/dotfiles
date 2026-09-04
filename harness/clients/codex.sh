#!/usr/bin/env bash
# The tracked top-level Codex settings, reconciled into ~/.codex/config.toml.
#
# Usage: codex.sh [config.toml] [tracked.toml]
#
# Same contract as statusline/codex.sh, which reconciles the [tui] half of the
# same file: prints the reconciled config on stdout and exits 0 when something
# changed, exits 3 when the config already says this, having written nothing,
# and exits 2 naming the file it could not read. The caller owns the write, so
# harness/install.sh takes its backup only on a real change.
#
# "Already correct" is 3 rather than the catch-all 1 for the reason the Claude
# half carries the same three codes: a crash exits 1 too, and a caller reading
# that as "nothing to do" leaves the tracked keys unwritten while the run
# reports success. check_links re-runs this script to verify the write, so an
# overloaded 1 would have confirmed its own silence.

set -euo pipefail

config="${1:-$HOME/.codex/config.toml}"
tracked="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/codex.toml}"

# Textual rather than parsed, for the reason statusline/codex.sh gives: tomllib
# needs Python 3.11 and the system python3 macOS ships is older. Only the lines
# above the first table header are touched, because a key this file owns can
# also be a legitimate key inside somebody else's table.
#
# A line carrying a key this file owns is replaced whole, so a trailing comment
# on one is lost. Splitting it off would need to know where the value ends, and
# a `#` inside a quoted value would be mis-split into a comment, which corrupts
# the value rather than preserving a note about it. Put a note about an owned
# key on its own line above it, or in clients/codex.toml.
exec python3 - "$config" "$tracked" <<'PY'
import pathlib, re, sys

config, tracked = (pathlib.Path(argument) for argument in sys.argv[1:3])


def read(path, missing_is_empty=False):
    try:
        return path.read_text()
    except FileNotFoundError:
        if missing_is_empty:
            return ""
        print(f"{path}: not found", file=sys.stderr)
        raise SystemExit(2)
    except (OSError, UnicodeDecodeError) as error:
        print(f"{path}: {error}", file=sys.stderr)
        raise SystemExit(2)


managed = {}
for line in read(tracked).splitlines():
    key = re.match(r"\s*([A-Za-z0-9_.-]+)\s*=", line)
    if key:
        managed[key.group(1)] = line.strip()

current = read(config, missing_is_empty=True)
head, tail, written = [], [], set()
for line in current.splitlines():
    if tail or line.lstrip().startswith("["):
        tail.append(line)
        continue
    key = re.match(r"\s*([A-Za-z0-9_.-]+)\s*=", line)
    if key and key.group(1) in managed:
        # A repeated key is invalid TOML, so a duplicate is dropped rather
        # than reconciled twice.
        if key.group(1) not in written:
            written.add(key.group(1))
            head.append(managed[key.group(1)])
        continue
    head.append(line)

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
head += [line for key, line in managed.items() if key not in written]
head += blanks

text = "\n".join(head + tail).strip("\n") + "\n"
if text == current:
    raise SystemExit(3)
sys.stdout.write(text)
PY
