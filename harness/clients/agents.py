#!/usr/bin/env python3
"""Render the canonical reviewer roles into one agent definition per client.

Usage: agents.py [--check] <roles-dir> <output-dir>

Generation writes <output-dir>/<client>/<file> for every role and client, removes any other file under <output-dir>, and prints the enforcement gaps and unverified capabilities. It exits 0 when it wrote or removed something and 3 when the output already matched, the same codes clients/codex.sh uses, so a crash cannot pass for "nothing to do". A role that is incomplete or asks for more than read-search access exits 4 before anything is written.

Output paths and their ancestors must not be symlinks; both generation and checking refuse them before reconciliation.

--check writes nothing. It reports each output that is missing, drifted, unmanaged, or no longer carries its client's restrictions, and exits 1 when it found any.

The output directory is wholly owned: install.sh links client agent paths to these files and never writes a definition into a client directory itself, which is what keeps a private agent beside them untouched.
"""

import re
import sys
from pathlib import Path

CLAUDE_TOOLS = "tools: Read, Grep, Glob"
CODEX_SANDBOX = 'sandbox_mode = "read-only"'
# Every role carries this Access line. Codex has no file-reading tool, so its definitions swap in a line that allows reading through shell and nothing else.
ACCESS = "Read and search only. Read and search the repository to follow callers and context. Never edit a file, run a command, fetch from the web, or delegate to another agent, even where the client would let you."
CODEX_ACCESS = "Read and search only. Read and search the repository to follow callers and context. Never edit a file, fetch from the web, or delegate to another agent, even where the client would let you. Shell is how this client reads files, so run only commands that read or search, never one that changes state."
# Disabled per agent through the documented mcp_servers key. Whether that overrides a server the parent registered is unverified.
CODEX_MCP = "\n[mcp_servers.agent-browser]\nenabled = false\n\n[mcp_servers.engram]\nenabled = false\n"
# OpenCode appends an agent's rules after its defaults and the last matching rule wins, so this denies every permission and re-allows only reading. Whether MCP tools resolve through the same wildcard is unverified. The read patterns keep the default .env guard, which a bare `read: allow` would override.
OPENCODE_PERMISSION = """permission:
  "*": deny
  read:
    "*": allow
    "*.env": deny
    "*.env.*": deny
    "*.env.example": allow
  grep: allow
  glob: allow
  list: allow
"""

# Known from each client's documentation. What no control covers is a gap; what a control should cover but only an installed client can prove is unverified.
GAPS = (
    "gap: codex: shell stays available inside the read-only sandbox, because shell is how a Codex agent reads files; writes are what the sandbox blocks",
    "gap: codex: no documented per-agent control disables web search or nested delegation",
    "gap: opencode: a diff file outside the project needs external_directory, which the agent's * deny refuses, so reviewers there take the inline fallback",
)
UNVERIFIED = (
    "unverified: every restriction above is static configuration until an installed client is probed at runtime",
    "unverified: codex and claude loading an agent definition through a symlink",
    "unverified: claude reading a diff file outside the project without a permission prompt",
    "unverified: opencode applying the * deny to MCP tools",
    "unverified: codex honoring the per-agent mcp_servers override for agent-browser and engram, which are registered globally",
    "unverified: codex loading an agent whose mcp_servers entry names a server this machine never registered",
    "unverified: the ccyolo, cyolo, and ocyolo launchers leaving agent restrictions in force, since each bypasses or overrides the parent's permissions",
    "unverified: diff delivery's inline fallback and escalation, which are protocol rather than exercised behavior",
)


def fail(message, status):
    print(message, file=sys.stderr)
    raise SystemExit(status)


def load(path):
    match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", path.read_text(), re.S)
    if not match:
        fail(f"{path}: missing frontmatter", 4)
    fields = dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)
    body = match.group(2).strip()
    if not re.fullmatch(r"[a-z][a-z0-9-]*", fields.get("name", "")):
        fail(f"{path}: name must be lowercase letters, digits, and hyphens", 4)
    if not fields.get("description"):
        fail(f"{path}: missing description", 4)
    if fields.get("access") != "read-search":
        fail(f"{path}: access must be read-search", 4)
    if ACCESS not in body.splitlines():
        fail(f"{path}: missing the canonical Access line", 4)
    if not body or "'''" in body:
        fail(f"{path}: body must be non-empty and free of '''", 4)
    return fields["name"], fields["description"], body


def render(roles):
    definitions = [load(path) for path in sorted(roles.glob("*.md"))]
    if sorted(name for name, _, _ in definitions) != ["reviewer-a", "reviewer-b"]:
        fail(f"{roles}: expected exactly one reviewer-a and one reviewer-b", 4)
    outputs = {}
    for name, description, body in definitions:
        # JSON string quoting is valid in both YAML and TOML for this text.
        quoted = '"' + description.replace("\\", "\\\\").replace('"', '\\"') + '"'
        outputs[f"claude/{name}.md"] = f"---\nname: {name}\ndescription: {quoted}\n{CLAUDE_TOOLS}\n---\n\n{body}\n"
        # Codex agent names allow only lowercase letters, digits, and underscores.
        codex = name.replace("-", "_")
        outputs[f"codex/{codex}.toml"] = f"name = \"{codex}\"\ndescription = {quoted}\n{CODEX_SANDBOX}\ndeveloper_instructions = '''\n{body.replace(ACCESS, CODEX_ACCESS)}\n'''\n{CODEX_MCP}"
        outputs[f"opencode/{name}.md"] = f"---\ndescription: {quoted}\nmode: subagent\n{OPENCODE_PERMISSION}---\n\n{body}\n"
    return outputs


def restricted(relative, text):
    lines = text.splitlines()
    if relative.startswith("claude/"):
        head = lines[: lines.index("---", 1)] if lines.count("---") >= 2 else lines
        return [line for line in head if line.startswith(("tools:", "disallowedTools:"))] == [CLAUDE_TOOLS]
    if relative.startswith("codex/"):
        return [line for line in lines if line.startswith("sandbox_mode")] == [CODEX_SANDBOX] and text.endswith(CODEX_MCP)
    head = text.split("---\n")[1] if text.startswith("---\n") else ""
    kept = "".join(line + "\n" for line in head.splitlines() if not line.startswith("description:"))
    return kept == f"mode: subagent\n{OPENCODE_PERMISSION}"


def existing(output):
    return {str(path.relative_to(output)): path for path in output.rglob("*") if path.is_file()} if output.is_dir() else {}


def check(outputs, output):
    present = existing(output)
    findings = [f"unmanaged: {relative}" for relative in sorted(set(present) - set(outputs))]
    for relative, expected in outputs.items():
        if relative not in present:
            findings.append(f"missing: {relative}")
            continue
        actual = present[relative].read_text()
        if not restricted(relative, actual):
            findings.append(f"widened: {relative}")
        elif actual != expected:
            findings.append(f"changed: {relative}")
    if findings:
        print("\n".join(findings))
    return 1 if findings else 0


def generate(outputs, output):
    changed = False
    for relative, path in existing(output).items():
        if relative not in outputs:
            path.unlink()
            changed = True
    for relative, text in outputs.items():
        path = output / relative
        if path.is_file() and path.read_text() == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        changed = True
    print("\n".join(GAPS + UNVERIFIED))
    return 0 if changed else 3


def main(argv):
    checking = argv[:1] == ["--check"]
    arguments = argv[1:] if checking else argv
    if len(arguments) != 2:
        fail(__doc__.splitlines()[2], 2)
    roles, output = (Path(argument) for argument in arguments)
    outputs = render(roles)
    for relative in outputs:
        path = output / relative
        for entry in (path, *path.parents):
            if entry.is_symlink():
                fail(f"{entry}: symlink in reviewer output path", 1 if checking else 4)
    return check(outputs, output) if checking else generate(outputs, output)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
