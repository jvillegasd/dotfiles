---
name: seo
description: Run the portable SEO package through isolated technical, content, schema, sitemap, performance, and visual roles.
license: MIT
metadata:
  upstream: "AgriciDaniel/claude-seo"
  opencode/autoinvoke: "false"
---

# Portable SEO

This local orchestrator adapts the attributed `AgriciDaniel/claude-seo`
package for Codex, Claude Code, and OpenCode. Treat committed references as
baseline guidance. Verify current thresholds, deprecations, crawler behavior,
and recommendations against primary sources before reporting them.

For a full audit, assign six isolated roles:

- technical -> `seo-technical`
- content -> `seo-content`
- schema -> `seo-schema`
- sitemap -> `seo-sitemap`
- performance -> `seo-performance`
- visual -> `seo-visual`

Run roles in parallel when supported and sequentially otherwise. Give each
role only the URL, requested scope, relevant raw evidence, and output contract.
Aggregate evidence without inventing measurements. Mark unavailable field
data, credentials, browser rendering, or crawl coverage as limitations.

For a narrower request, load only the matching locked skill: `seo-page`,
`seo-competitor-pages`, `seo-geo`, `seo-hreflang`, `seo-images`, `seo-plan`, or
`seo-programmatic`. `seo-audit` remains a pristine upstream reference; use this
portable six-role flow instead of its client-specific delegation commands.

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

## Nested skills

- `seo-technical`, `seo-content`, `seo-schema`, `seo-sitemap`
- `seo-performance`, `seo-visual`
- `seo-page`, `seo-competitor-pages`, `seo-geo`, `seo-hreflang`, `seo-images`,
  `seo-plan`, `seo-programmatic` when the request selects that branch
