---
name: performance
description: Internal portable SEO role for measured performance and Core Web Vitals evidence.
license: MIT
disable-model-invocation: true
metadata:
  upstream: "AgriciDaniel/claude-seo"
  opencode/autoinvoke: "false"
---

# SEO Performance Role

Use field data first (CrUX or PageSpeed Insights) when available. Distinguish
field Core Web Vitals from lab diagnostics and source-only heuristics. Verify
current thresholds and tool behavior against Google or Chrome primary sources
at runtime.

If measurement requires local Lighthouse, run it only after this role is
explicitly nested by `seo`. Use an existing installation first; otherwise use
an ephemeral `npx` cache outside the repository. Never install browser tooling
during the default harness setup.

Report evidence, collection time, device/profile, limitations, and prioritized
bottlenecks. Never convert a source-code guess into a measured score.
