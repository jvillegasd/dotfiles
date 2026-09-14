#!/usr/bin/env python3
"""Render every assigned role into one agent definition per client.

Usage: agents.py [--check] <assignments.json> <output-dir>

The assignments file is the one source for roles and their model and effort. `clients` sets each client's default model and effort, and `inherit` there means the session's own choice. Each entry under `roles` names its canonical definition, relative to the assignments file, and may override either field per client. A field resolves from the role's override, else the client default, and generation prints every resolution with its source. A role with no definition is an assignment waiting for its role: it is validated and reported, and nothing is generated for it.

Generation writes <output-dir>/<client>/<role>.md for every defined role and client, removes any other file under <output-dir>, and prints the resolved assignments, the enforcement gaps, and the unverified capabilities. It exits 0 when it wrote or removed something and 3 when the output already matched, so a crash cannot pass for "nothing to do". An invalid or unsupported assignment, an incomplete role, a role asking for other access than its own, or a missing required role exits 4 before anything is written; nothing is substituted.

Output paths and their ancestors must not be symlinks; both generation and checking refuse them before reconciliation.

--check writes nothing. It reports each output that is missing, drifted, unmanaged, or no longer carries its access level's restrictions, and exits 1 when it found any.

The output directory is wholly owned: install.sh links client agent paths to these files and never writes a definition into a client directory itself, which is what keeps a private agent beside them untouched.
"""

import json
import re
import sys
from pathlib import Path

# adversarial-review launches the reviewers and the refuter and POLICY.md names the executor, so each must exist with exactly this access. Every other role is read-search: only the executor may implement.
REQUIRED = {"executor": "implement", "review-refuter": "read-search", "reviewer-a": "read-search", "reviewer-b": "read-search"}
# Documented agent frontmatter values: https://code.claude.com/docs/en/sub-agents (model, effort) and https://opencode.ai/docs/agents/ (model, plus provider options such as OpenAI's reasoningEffort). OpenCode passes effort to the provider, so it is accepted only beside an openai/ model.
SUPPORTED = {
    "claude": {"model": r"inherit|sonnet|opus|haiku|fable|claude-[a-z0-9.-]+", "effort": r"inherit|low|medium|high|xhigh|max"},
    "opencode": {"model": r"inherit|[a-z0-9._-]+/[A-Za-z0-9._:/-]+", "effort": r"inherit|none|minimal|low|medium|high|xhigh"},
}
ACCESS = "Read and search only. Read and search the repository to follow callers and context. Never edit a file, run a command, fetch from the web, or delegate to another agent, even where the client would let you."
CLAUDE_CONTROLS = {"read-search": ["tools: Read, Grep, Glob"], "implement": ["disallowedTools: Agent"]}
# OpenCode appends an agent's rules after its defaults and the last matching rule wins. A reviewer denies every permission and re-allows only reading, keeping the default .env guard a bare `read: allow` would override; whether MCP tools resolve through the same wildcard is unverified. The executor keeps the defaults and denies delegation plus the commit, push, worktree, and forge commands its parent owns.
OPENCODE_CONTROLS = {
    "read-search": """permission:
  "*": deny
  read:
    "*": allow
    "*.env": deny
    "*.env.*": deny
    "*.env.example": allow
  grep: allow
  glob: allow
  list: allow
""",
    "implement": """permission:
  task: deny
  bash:
    "git commit*": deny
    "git push*": deny
    "git worktree remove*": deny
    "wt remove*": deny
    "wt merge*": deny
    "wt step commit*": deny
    "gh *": deny
""",
}

# Known from each client's documentation. What no control covers is a gap; what a control should cover but only an installed client can prove is unverified.
GAPS = (
    "gap: opencode: a diff file outside the project needs external_directory, which the agent's * deny refuses, so reviewers and the refuter there take the inline fallback",
    "gap: opencode: a standards file outside the project, such as the installed ponytail body, needs the same external_directory, so reviewers there get it inline after their loaded: line omits it",
    "gap: claude: the executor keeps Bash, because a disallowedTools specifier removes the whole tool, so its commit, push, pull request, merge, and tracker limits are instructions only",
    "gap: claude: a model parameter passed at launch overrides an agent's model frontmatter, and an availableModels allowlist substitutes a blocked model with a warning, so the policy forbids the parameter and neither is enforced",
    "gap: opencode: the executor's bash denies match command prefixes, so the same action spelled another way is not denied",
)
UNVERIFIED = (
    "unverified: every restriction above is static configuration until an installed client is probed at runtime",
    "unverified: claude loading an agent definition through a symlink",
    "unverified: claude reading a diff or standards file outside the project without a permission prompt",
    "unverified: opencode applying the * deny to MCP tools",
    "unverified: the ccyolo and ocyolo launchers leaving agent restrictions in force, since each bypasses or overrides the parent's permissions",
    "unverified: diff delivery's inline fallback and escalation, which are protocol rather than exercised behavior",
    "unverified: claude running a subagent on its model and effort frontmatter, and on the session's effort when effort is absent",
    "unverified: opencode sending an agent's reasoningEffort with its model requests",
    "unverified: claude disallowedTools: Agent and opencode task: deny stopping the executor from delegating",
)


def fail(message, status):
    print(message, file=sys.stderr)
    raise SystemExit(status)


def unique(pairs):
    keys = [key for key, _ in pairs]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        fail(f"duplicate keys: {', '.join(duplicates)}", 4)
    return dict(pairs)


def load(path, name):
    try:
        text = path.read_text()
    except OSError as error:
        fail(f"{path}: unreadable definition for {name}: {error.strerror}", 4)
    match = re.fullmatch(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not match:
        fail(f"{path}: missing frontmatter", 4)
    front = dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)
    body = match.group(2).strip()
    if front.get("name") != name:
        fail(f"{path}: name must be {name}, the role it is assigned to", 4)
    if not front.get("description"):
        fail(f"{path}: missing description", 4)
    access = front.get("access")
    expected = REQUIRED.get(name, "read-search")
    if access != expected:
        fail(f"{path}: access must be {expected}", 4)
    if access == "read-search" and ACCESS not in body.splitlines():
        fail(f"{path}: missing the canonical Access line", 4)
    if not body or "'''" in body:
        fail(f"{path}: body must be non-empty and free of '''", 4)
    return front["description"], access, body


def assignment_block(block, label):
    if not isinstance(block, dict):
        fail(f"{label} must be an object", 4)
    unknown = sorted(set(block) - {"model", "effort"})
    if unknown:
        fail(f"{label}: unknown keys {', '.join(unknown)}; only model and effort are assigned", 4)
    return block


def resolve(config):
    """Return the roles and {(client, role): {field: (value, source)}} for every assigned role, or exit 4 on the first invalid assignment."""
    clients = config.get("clients") if isinstance(config, dict) else None
    roles = config.get("roles") if isinstance(config, dict) else None
    if not isinstance(clients, dict) or sorted(clients) != sorted(SUPPORTED):
        fail(f"clients must set exactly {', '.join(SUPPORTED)}", 4)
    if not isinstance(roles, dict):
        fail("roles must be an object", 4)
    resolved = {}
    for name, role in sorted(roles.items()):
        # The name becomes an output path, so nothing but a plain file name gets through.
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            fail(f"roles.{name!r}: a role name is lowercase letters, digits, and hyphens", 4)
        if not isinstance(role, dict):
            fail(f"roles.{name} must be an object", 4)
        unknown = sorted(set(role) - {"definition", *SUPPORTED})
        if unknown:
            fail(f"roles.{name}: unknown keys {', '.join(unknown)}; a role takes definition, {', '.join(SUPPORTED)}", 4)
        if "definition" in role and not (isinstance(role["definition"], str) and role["definition"]):
            fail(f"roles.{name}.definition must be a path; leave it out for a role with no definition yet", 4)
        for client, patterns in SUPPORTED.items():
            default = assignment_block(clients[client], f"clients.{client}")
            override = assignment_block(role.get(client, {}), f"roles.{name}.{client}")
            settings = {}
            for field, pattern in patterns.items():
                if field not in default:
                    fail(f"clients.{client} must set {field}; write inherit to use the session's", 4)
                value, source = (override[field], "role") if field in override else (default[field], "client default")
                if not isinstance(value, str) or not re.fullmatch(pattern, value):
                    fail(f"{client} {field} {value!r} for {name} is unsupported; {client} accepts {pattern.replace('|', ', ')}", 4)
                settings[field] = (value, source)
            if client == "opencode" and settings["effort"][0] != "inherit" and not settings["model"][0].startswith("openai/"):
                fail(f"opencode effort for {name} is passed as OpenAI's reasoningEffort, so it needs an openai/ model, not {settings['model'][0]}", 4)
            resolved[client, name] = settings
    missing = [name for name in REQUIRED if "definition" not in roles.get(name, {})]
    if missing:
        fail(f"{', '.join(missing)} must be assigned with a definition", 4)
    return roles, resolved


def render(config_path):
    """Return {relative output: text}, {relative output: access}, and the report lines."""
    try:
        config = json.loads(config_path.read_text(), object_pairs_hook=unique)
    except (OSError, ValueError) as error:
        fail(f"{config_path}: {error}", 4)
    roles, resolved = resolve(config)
    outputs, accesses, report = {}, {}, []
    for (client, name), settings in sorted(resolved.items()):
        (model, model_source), (effort, effort_source) = settings["model"], settings["effort"]
        report.append(f"assignment: {client} {name} model={model} ({model_source}) effort={effort} ({effort_source})")
        if model != "inherit":
            report.append(f"unverified: {client} {name} model {model} is available to this account")
        if effort != "inherit":
            report.append(f"unverified: {client} {name} effort {effort} is supported by its model")
    for name, role in sorted(roles.items()):
        if "definition" not in role:
            report.append(f"pending: {name} has an assignment and no definition, so no agent is generated")
            continue
        description, access, body = load(config_path.parent / role["definition"], name)
        # JSON string quoting is valid YAML for this text.
        quoted = '"' + description.replace("\\", "\\\\").replace('"', '\\"') + '"'
        claude, opencode = resolved["claude", name], resolved["opencode", name]
        # Claude Code documents model: inherit and inherits effort when the field is absent; OpenCode inherits both when absent.
        claude_settings = f"model: {claude['model'][0]}\n" + ("" if claude["effort"][0] == "inherit" else f"effort: {claude['effort'][0]}\n")
        opencode_settings = ("" if opencode["model"][0] == "inherit" else f"model: {opencode['model'][0]}\n") + ("" if opencode["effort"][0] == "inherit" else f"reasoningEffort: {opencode['effort'][0]}\n")
        controls = "".join(line + "\n" for line in CLAUDE_CONTROLS[access])
        outputs[f"claude/{name}.md"] = f"---\nname: {name}\ndescription: {quoted}\n{controls}{claude_settings}---\n\n{body}\n"
        outputs[f"opencode/{name}.md"] = f"---\ndescription: {quoted}\nmode: subagent\n{OPENCODE_CONTROLS[access]}{opencode_settings}---\n\n{body}\n"
        accesses[f"claude/{name}.md"] = accesses[f"opencode/{name}.md"] = access
    return outputs, accesses, report


def restricted(relative, text, access):
    lines = text.splitlines()
    if relative.startswith("claude/"):
        head = lines[: lines.index("---", 1)] if lines.count("---") >= 2 else lines
        return [line for line in head if line.startswith(("tools:", "disallowedTools:"))] == CLAUDE_CONTROLS[access]
    head = text.split("---\n")[1] if text.startswith("---\n") else ""
    kept = "".join(line + "\n" for line in head.splitlines() if not line.startswith(("description:", "model:", "reasoningEffort:")))
    return kept == f"mode: subagent\n{OPENCODE_CONTROLS[access]}"


def existing(output):
    return {str(path.relative_to(output)): path for path in output.rglob("*") if path.is_file()} if output.is_dir() else {}


def check(outputs, accesses, output):
    present = existing(output)
    findings = [f"unmanaged: {relative}" for relative in sorted(set(present) - set(outputs))]
    for relative, expected in outputs.items():
        if relative not in present:
            findings.append(f"missing: {relative}")
            continue
        actual = present[relative].read_text()
        if not restricted(relative, actual, accesses[relative]):
            findings.append(f"widened: {relative}")
        elif actual != expected:
            findings.append(f"changed: {relative}")
    if findings:
        print("\n".join(findings))
    return 1 if findings else 0


def generate(outputs, output, report):
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
    print("\n".join([*report, *GAPS, *UNVERIFIED]))
    return 0 if changed else 3


def main(argv):
    checking = argv[:1] == ["--check"]
    arguments = argv[1:] if checking else argv
    if len(arguments) != 2:
        fail(__doc__.splitlines()[2], 2)
    config, output = (Path(argument) for argument in arguments)
    outputs, accesses, report = render(config)
    for relative in outputs:
        path = output / relative
        for entry in (path, *path.parents):
            if entry.is_symlink():
                fail(f"{entry}: symlink in role agent output path", 1 if checking else 4)
    return check(outputs, accesses, output) if checking else generate(outputs, output, report)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
