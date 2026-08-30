# Portable AI harness

One committed source for Codex, Claude Code, and OpenCode:

- `POLICY.md` is linked to each client's global instruction path.
- `skills/` contains locked third-party bodies and local workflow wrappers.
- `install.sh` installs current clients/integrations, preserves mutable client
  state, and reconciles policy and skill links individually.
- `tests/test_harness.py` checks supply-chain and installer invariants.

## Install

The root `../install.sh` installs the harness by default. To reconcile only
policy and skills:

```sh
./harness/install.sh --links-only
```

The full installer uses Homebrew for Codex, OpenCode, GitHub CLI, Engram, UV,
RTK, and Worktrunk; Anthropic's native latest channel for Claude Code; and official
client setup/plugin commands for Engram, Ponytail, and RTK. It never starts an
interactive client or authenticates for you.

It also links the portable `claude-seo` launcher. SEO Python dependencies and
Chromium remain lazy and live only in the ignored per-user harness cache.

## Third-party skill updates

`.agents/skills` points to `harness/skills`. Every standalone third-party skill
is installed with skills.sh and committed with its `skills-lock.json` entry:

```sh
npx skills@1 add <owner>/<repo> --skill <name> --agent universal -y
ln -s ../../.agents/skills/<name> .claude/skills/<name>
```

Review the installed body and security report before committing. Locked bodies
stay pristine; behavior changes belong in a local wrapper or `POLICY.md`.

To check and deliberately update all locked bodies:

```sh
npx skills@1 update --project --yes
git diff -- harness/skills skills-lock.json .claude/skills
```

Review every upstream diff, run the acceptance suite, and commit only the
approved update. Provisioning never runs `skills add`, `skills update`, or a
lockfile restore command.

Delete a locked skill in one reviewed change: remove
`harness/skills/<name>`, its `skills-lock.json` entry, and
`.claude/skills/<name>`. A copied skill with unknown provenance remains an
attributed local fork until its exact upstream is identified.

Engram, Ponytail, and Orca-provided skills are runtime/plugin managed and never
belong in `skills-lock.json`.

## Roster

Locked Matt Pocock skills provide grilling, domain/module vocabulary, TDD,
research/prototyping, diagnosis/review, handoff, conflict resolution, setup,
and spec/ticket primitives. Locked `AgriciDaniel/claude-seo` skills provide SEO
domain primitives.

Local explicit workflow entries are `grill-me`, `setup-harness`, `spec`,
`tickets`, `ship`, and `address-review`. `seo` is the portable SEO
orchestrator; `seo-performance` and `seo-visual` are its local internal roles.

## GitHub lifecycle

`setup-harness` writes `docs/agents/harness.json`, creates the four configured
labels, writes the Matt-skill tracker compatibility file, and copies the
workflow and reconciler bundled in its skill directory. The workflow becomes
active when that human-reviewed change reaches the default branch. GitHub
native sub-issue and dependency relationships remain the source of truth. A
blocker satisfies the ready frontier only when a merged pull request closed it;
the parent closes only after every child has that same merge evidence. Closing
or reopening a child always reconciles both states.

## Validation

```sh
python3 harness/tests/test_harness.py
```

The suite validates shell/Python syntax, unique skill names, lock hashes,
Claude bookkeeping links, local-vs-locked separation, secret/generated-state
exclusions, installer safety, collision backups, retired aliases,
idempotency, and GitHub close/reopen behavior.
