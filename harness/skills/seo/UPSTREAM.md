# SEO runtime attribution

The launcher, runtime, and supporting scripts in this local portability layer
derive from [`AgriciDaniel/claude-seo`](https://github.com/AgriciDaniel/claude-seo)
at commit `a1480c7e590b16001bd9dc1627eacdcd44d580f9` (MIT).

The launcher sets `CLAUDE_SEO_DATA_DIR` to the portable harness cache so mutable
virtualenv, browser, and runtime state never enter the committed skill body.
Standalone upstream skill bodies remain separately pristine and locked in
`skills-lock.json`.
