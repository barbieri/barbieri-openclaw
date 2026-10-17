# Gustavo Style

Canonical source: [barbieri-playground/design/DESIGN.md](../../barbieri-playground/design/DESIGN.md), revision `d581806`.
This repository adopts that system, not a separate design specification.
Generated includes contain the canonical table values for self-contained offline email and report rendering.
Do not edit generated tokens by hand. Refresh with the exporter in
`barbieri-openclaw/scripts/export_gustavo_style.py`, passing the canonical document,
the include destination, and `--format python|typescript|css|hbs`.

Themes follow `prefers-color-scheme`; documents also support `data-theme="light"`
and `data-theme="dark"` on the root. Explicit surfaces prevent transparent-background failures.
Roboto and Open Sans use local system fallbacks when mail clients strip web fonts.

## Verification evidence

The light and dark screenshots under `proof/` show synthetic content rendered by the
real HTML builders in Chromium. The browser preferred theme and explicit root
`data-theme` override were both checked. `proof/results.json` records computed
surface, text, and font values. No email was sent.

These are browser-theme checks, not screenshots from a logged-in Gmail client
or the installed OpenClaw dashboard. Gmail-specific rewriting remains unverified.
