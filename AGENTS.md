# AGENTS.md

This repository stores reusable OpenClaw-related automations.

## Rules

- Keep repository-owned public code free of personal addresses, tokens, passwords, account aliases, and hostnames. Locked upstream skill copies may retain approved public references; `scripts/audit_public_source.py` scans them for private values.
- Configuration must come from command-line arguments or environment variables.
- Never commit machine-specific absolute user-home paths. Use `~` in documentation,
  `Path(...).expanduser()` in Python, and `$HOME` in shell scripts.
- Prefer small, testable Python modules over shell wrappers with embedded state.
- Python projects use `uv`; do not install Python packages with manual `pip` commands.
- Install Python CLIs for user-level use with `uv tool install --force --editable .`.
- Do not copy application source code from another project into this repository. Reuse external
  code through a dependency or import. If the external project does not expose a reusable
  interface, stop and ask the requester before adding its code here. Project-local skills
  installed with `npx skills` and tracked in `skills-lock.json` are the exception.
- Before starting a whole-project language rewrite or another migration of comparable size, explain
  the scope, expected behavior changes, and estimated work. Proceed only after the requester gives
  explicit approval. A request to investigate why a language or dependency exists does not authorize
  a rewrite.
- Keep commits atomic and history linear whenever possible.
- For nontrivial implementation, follow `.agents/skills/poteto-mode/SKILL.md`. Before publishing
  the branch, review its diff with `.agents/skills/thermos/SKILL.md` and address its findings.
- For Codex, use native subagents for upstream `Task` roles. In Thermos,
  give one reviewer `.agents/skills/thermo-nuclear-review/SKILL.md` and another
  `.agents/skills/thermo-nuclear-code-quality-review/SKILL.md`, then synthesize
  their findings.
- Before a pull request, inspect every commit since the merge-base. Fold corrections to code
  introduced in this branch into the introducing commit with a fixup and autosquash. Keep a
  separate commit for an independent improvement or a fix to base-branch code. Use
  `.agents/skills/git-history-cleanup/SKILL.md` when a private linear series needs regrouping.
- Add a test only when it proves a distinct behavior or regression that existing tests do not
  cover. Keep the repository's existing QA gates.
- At the end of work, reflect on test failures, review feedback, and other new knowledge.
  Record durable lessons in the owning guidance or feature documentation in the relevant
  original commit, often the first commit for branch-wide rules. Do not add transient failures
  as permanent rules. Use `.agents/skills/reflect/SKILL.md` when explicitly asked for a full
  transcript retrospective.
- Never change non-owned installed skills under project `.agents/skills/`,
  `~/.agent/skills/`, or `~/.agents/skills/` as part of self-update when a skill
  lock tracks them. Record an upstream issue or proposal instead. Refreshing
  upstream dependencies with `npx skills update` is a separate maintenance task.
  For a skill we own in `barbieri-playground/skills/`, fix its source there,
  open a pull request for review, and update this repository only after merge.
- Before creating or amending any commit, spawn an independent review subagent with no access to
  the implementation session. Give the reviewer only the original user request, the proposed
  commit message, and the changes to review. Require the reviewer to use the
  `.agents/skills/thermo-nuclear-code-quality-review/SKILL.md`. Address its findings and repeat
  the independent review until the commit passes all of these checks:
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

## Agent skills

### Issue tracker

Issues and specs live in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.
Use `.agents/skills/setup-matt-pocock-skills/SKILL.md` when changing this setup and
`.agents/skills/code-review/SKILL.md` for a spec-linked branch review.

### Triage labels

Use the default five triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use one root glossary and `docs/adr/` for decisions. See `docs/agents/domain.md`.
