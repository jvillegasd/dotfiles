#!/usr/bin/env bash
# The tracked top-level Codex settings, reconciled into ~/.codex/config.toml.
#
# Usage: codex.sh [config.toml] [tracked.toml]
#
# Same contract as statusline/codex.sh, which reconciles the [tui] half of the
# same file: prints the reconciled config on stdout and exits 0 when something
# changed, exits 1 when the config already says this, having written nothing.
# The caller owns the write, so harness/install.sh takes its backup only on a
# real change.

set -euo pipefail

config="${1:-$HOME/.codex/config.toml}"
tracked="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/codex.toml}"

# Textual rather than parsed, for the reason statusline/codex.sh gives: tomllib
# needs Python 3.11 and the system python3 macOS ships is older. Only the lines
# above the first table header are touched, because a key this file owns can
# also be a legitimate key inside somebody else's table.
exec python3 - "$config" "$tracked" <<'PY'
import pathlib, re, sys

config, tracked = (pathlib.Path(argument) for argument in sys.argv[1:3])

managed = {}
for line in tracked.read_text().splitlines():
    key = re.match(r"([A-Za-z0-9_.-]+)\s*=", line)
    if key:
        managed[key.group(1)] = line.rstrip()

current = config.read_text() if config.exists() else ""
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

# A missing key goes after the last one that is already there, and whatever
# blank lines separated that block from the first table are put back exactly.
# Rewriting the separator instead is what cost this reconciler its fixed point:
# `engram setup` writes its own keys without one, so the two took turns adding
# and dropping a blank line and every run rewrote the file.
blanks = []
while head and not head[-1].strip():
    blanks.append(head.pop())
head += [line for key, line in managed.items() if key not in written]
head += blanks

text = "\n".join(head + tail).strip("\n") + "\n"
if text == current:
    raise SystemExit(1)
sys.stdout.write(text)
PY
