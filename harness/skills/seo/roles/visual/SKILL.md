---
name: visual
description: Internal portable SEO role for desktop/mobile rendering and above-the-fold evidence.
license: MIT
disable-model-invocation: true
metadata:
  upstream: "AgriciDaniel/claude-seo"
  opencode/autoinvoke: "false"
---

# SEO Visual Role

Prefer an available client browser or screenshot tool. If none exists, lazily
create an isolated environment under
`${XDG_CACHE_HOME:-$HOME/.cache}/portable-harness/seo`, install Playwright
there, and set `PLAYWRIGHT_BROWSERS_PATH` to that cache before installing
Chromium. Reuse the cache on later runs.

Capture desktop and mobile evidence, then check visible heading/CTA hierarchy,
horizontal overflow, overlapping or clipped content, responsive navigation,
image loading, and layout shifts observable during load. Preserve screenshots
only in the user-selected audit output; never write browsers, virtualenvs, or
generated screenshots into the harness.

State viewport sizes, capture time, rendering failures, blocked resources, and
authentication limitations. Do not infer visual behavior from HTML when a
render was requested but unavailable.
