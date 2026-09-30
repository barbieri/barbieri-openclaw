# AGENTS.md

This repository stores reusable OpenClaw-related automations.

## Rules

- Keep public code free of personal addresses, tokens, passwords, account aliases, and hostnames.
- Configuration must come from command-line arguments or environment variables.
- Prefer small, testable Python modules over shell wrappers with embedded state.
- Python projects use `uv`; do not install Python packages with manual `pip` commands.
- Install Python CLIs for user-level use with `uv tool install --force --editable .`.
- Do not copy source code from another project into this repository. Reuse external code through a
  dependency or import. If the external project does not expose a reusable interface, stop and ask
  the requester before adding any of its code here.
- Before starting a whole-project language rewrite or another migration of comparable size, explain
  the scope, expected behavior changes, and estimated work. Proceed only after the requester gives
  explicit approval. A request to investigate why a language or dependency exists does not authorize
  a rewrite.
- Keep commits atomic and history linear whenever possible.
- If a fix belongs to an existing commit that has not been pushed, amend that commit or use an
  interactive rebase. Do not leave a known defect and its fix as separate commits in the same
  changeset or pull request.
- Before creating or amending any commit, spawn an independent review subagent with no access to
  the implementation session. Give the reviewer only the original user request, the proposed
  commit message, and the changes to review. Require the reviewer to use the
  `thermo-nuclear-code-quality-review` skill. Address its findings and repeat the independent
  review until the commit passes all of these checks:
  - The change contains no private or personal information.
  - Production code contains no hardcoded URLs or IDs. Supply them through environment variables,
    configuration files, or command-line arguments. Synthetic test fixtures may use reserved
    example URLs and obviously fake IDs. Do not require changes to such fixtures.
  - Every addition has a clear purpose that existing code cannot satisfy. Remove bloat and explain
    changes to higher-level or entry-point functions in the commit message.
  - The change preserves existing behavior. Do not change or disable unit tests unless the original
    request explicitly requires it. If such a test change becomes necessary without prior approval,
    stop and ask the requester before proceeding. Explain behavior-preservation decisions for
    higher-level or entry-point functions in the commit message.
  - Delete unused code and other leftovers. Describe material deletions from higher-level or
    entry-point functions in the commit message.
  - The commit message states what the original request asked for and explains what changed, why it
    changed, and how the implementation works.
- Validate changes before publishing:
  - `uv run pytest`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run pre-commit run --all-files`

## Layout

- `skills/` contains reusable automations or skill-adjacent code.
- Each skill should include its own README and focused tests when behavior is non-trivial.
- Python CLIs must be exposed through `pyproject.toml` project scripts.
