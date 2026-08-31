---
name: seo
description: Run the portable SEO package through isolated technical, content, schema, sitemap, performance, and visual roles.
license: MIT
disable-model-invocation: true
metadata:
  upstream: "AgriciDaniel/claude-seo"
  opencode/autoinvoke: "false"
---

# Portable SEO

This local orchestrator adapts the attributed `AgriciDaniel/claude-seo`
package for Codex, Claude Code, and OpenCode. Treat committed references as
baseline guidance. Verify current thresholds, deprecations, crawler behavior,
and recommendations against primary sources before reporting them.

`seo` is the only SEO name any client installs. Every role below is a body read
from a path, never an invocable skill, so nothing here can fire on a
description match. Locked upstream bodies stay pristine as sibling directories
of this one, at `../seo-<role>/SKILL.md`; the two roles that have no upstream
body are local forks under `roles/`.

For a full audit, assign six isolated roles:

- technical -> `../seo-technical/SKILL.md`
- content -> `../seo-content/SKILL.md`
- schema -> `../seo-schema/SKILL.md`
- sitemap -> `../seo-sitemap/SKILL.md`
- performance -> `roles/performance` in this skill directory
- visual -> `roles/visual` in this skill directory

Run roles in parallel when supported and sequentially otherwise. Give each
role only the URL, requested scope, relevant raw evidence, and output contract.
Aggregate evidence without inventing measurements. Mark unavailable field
data, credentials, browser rendering, or crawl coverage as limitations.

For a narrower request, read only the matching sibling body: `../seo-page/`,
`../seo-competitor-pages/`, `../seo-geo/`, `../seo-hreflang/`, `../seo-images/`,
`../seo-plan/`, or `../seo-programmatic/`. `../seo-audit/` remains a pristine
upstream reference; use this portable six-role flow instead of its
client-specific delegation commands.

Write generated audits and screenshots outside the harness source unless the
user names an output path. Heavy browser dependencies are installed lazily by
the role that needs them.

The bundled `scripts/` and `references/` are an attributed local
fork for deterministic collection and baseline checks. Use only the files the
selected branch needs. If their imports are unavailable, create a cache-hosted
virtualenv rather than a repository `.venv`; do not install them during the
default harness setup.

Commands in locked bodies written as `claude-seo run <script>` use the bundled
portable launcher. On first use, run `claude-seo setup --skip-browser`; omit
`--skip-browser` only for a role that needs rendered evidence. The launcher
stores its environment and browsers under
`${XDG_CACHE_HOME:-$HOME/.cache}/portable-harness/seo`. If the installer has not
linked the command yet, invoke `bin/claude-seo` from this skill directory.
Resolve upstream paths beginning `skills/seo/` against this same skill
directory, not the user's current project.

## Role bodies

All of these are files, not skills. Read them by path from this skill
directory; none of them is installed in any client.

- `../seo-technical/`, `../seo-content/`, `../seo-schema/`, `../seo-sitemap/`
- `roles/performance` and `roles/visual`
- `../seo-page/`, `../seo-competitor-pages/`, `../seo-geo/`,
  `../seo-hreflang/`, `../seo-images/`, `../seo-plan/`, `../seo-programmatic/`
  when the request selects that branch
