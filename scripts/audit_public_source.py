from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

SOURCE_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATTERNS = {
    "email address": re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    "user home path": re.compile(r"(?:/home/|/Users/)[^/\s]+|[A-Za-z]:\\+Users\\+[^\\\s]+"),
    "secret token": re.compile(
        r"\b(?:Bearer\s+[A-Za-z0-9._~+/=-]{3,}|(?:AKIA|ASIA)[0-9A-Z]{16}|"
        r"xox[baprs]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
        r"gh[pousr]_[A-Za-z0-9]{20,}|"
        r"github_pat_[A-Za-z0-9_]{20,})\b",
        re.IGNORECASE,
    ),
    "hardcoded ID": re.compile(
        r"\b(?:[CDGUW](?=[A-Z0-9]{8,}\b)(?=[A-Z0-9]*[0-9])[A-Z0-9]{8,}|"
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{12})\b"
    ),
}
URL_PATTERN = re.compile(r"https?://[^\s<>\"\u0027]+", re.IGNORECASE)
PUBLIC_URL_HOSTS = {
    "files.pythonhosted.org",
    "fsf.org",
    "pypi.org",
    "www.gnu.org",
}
PUBLIC_GITHUB_PATHS = {
    "/barbieri/barbieri-openclaw",
    "/barbieri/local-openfinance",
    "/openclaw/gogcli",
    "/openclaw/slacrawl",
    "/pre-commit/pre-commit-hooks",
}
VENDORED_PUBLIC_URL_HOSTS = {
    "cdn.jsdelivr.net",
    "cdn.tailwindcss.com",
    "dashboard.stripe.com",
    "github.com",
    "gitlab.com",
    "localhost",
    "reddit.com",
    "www.aihero.dev",
}
# Explicitly reviewed dotted references in the pinned upstream skill copies.
VENDORED_PUBLIC_BARE_HOSTS = {
    "0001-event-sourced-orders.md",
    "0001-slug.md",
    "0002-postgres-for-write-model.md",
    "0002-slug.md",
    "adr-format.md",
    "agent-brief.md",
    "agents.md",
    "asd-ste100.org",
    "authclient.refresh",
    "authoring-a-skill.md",
    "autonomous-run.md",
    "autopilot-full.md",
    "autopilot-stack.md",
    "babysit.md",
    "bad.tsv",
    "bootstrap.ts",
    "budget.json",
    "budget.mjs",
    "bug-fix.md",
    "bugbot-triage.md",
    "bun.lock",
    "bun.lockb",
    "cart.add",
    "cart.total",
    "check-plan.mjs",
    "check.bucket",
    "check.state",
    "children.tsv",
    "claude.md",
    "cli.ts",
    "client.charge",
    "client.ts",
    "code-quality-review.md",
    "command.slice",
    "comment.author",
    "comment.author.login",
    "comment.body",
    "comment.createdat",
    "comment.line",
    "comment.path",
    "commits.nodes",
    "contexts.nodes",
    "contexts.pageinfo",
    "contexts.pageinfo.endcursor",
    "contexts.pageinfo.hasnextpage",
    "contributing.md",
    "dark-mode.md",
    "decision.tsv",
    "decisions.tsv",
    "deepening.md",
    "dependency-cruiser.cjs",
    "dependency-cruiser.config.cjs",
    "design-it-twice.md",
    "design-red-flags.md",
    "developers.google.com",
    "diataxis.fr",
    "divergent-reviewer.md",
    "domain.md",
    "env.example",
    "eval.md",
    "example.com",
    "example.test.ts",
    "explainer-prompt.md",
    "explorer-prompt.md",
    "explorer.exe",
    "fakes.test-helper.ts",
    "feature.md",
    "frontier.json",
    "gates.md",
    "git-history-cleanup-after.diff",
    "git-history-cleanup-target.diff",
    "github.com",
    "github.ts",
    "gitlab.com",
    "glossary-format.md",
    "glossary-map.md",
    "glossary.md",
    "graphql-api.md",
    "gt-output.txt",
    "handler.ts",
    "hillclimb.md",
    "hitl-loop.template.sh",
    "html-report.md",
    "hunk.patch",
    "impl.ts",
    "index.ts",
    "investigation.md",
    "issue-tracker-github.md",
    "issue-tracker-gitlab.md",
    "issue-tracker-local.md",
    "issue-tracker.md",
    "items.reduce",
    "jest.mock",
    "json.gz",
    "judgment-reviewer.md",
    "lead-judgment.md",
    "learning-record-format.md",
    "ledger.tsv",
    "live.md",
    "logic.md",
    "main.js",
    "main.txt",
    "map.md",
    "mermaid.initialize",
    "message.content",
    "mission-format.md",
    "mission.md",
    "mocking.md",
    "mockpayment.process",
    "module.exports",
    "multi-phase-plan.md",
    "notes.md",
    "object.author",
    "opening-a-pr.md",
    "orch.lock",
    "orch.ts",
    "orchestrate.md",
    "order.total",
    "out-of-scope.md",
    "overview.md",
    "package-lock.json",
    "package.json",
    "pause-safely.md",
    "payload.json",
    "paymentclient.charge",
    "paymentservice.process",
    "perf-issue.md",
    "performance.now",
    "phase-boundaries.md",
    "plan.md",
    "plugin-system.md",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "policy.ts",
    "preferences.md",
    "process.argv.slice",
    "process.env",
    "process.exitcode",
    "prototype.md",
    "pstack-models.mdc",
    "rationale-template.md",
    "readme.md",
    "refactoring.md",
    "render.ts",
    "request.baserefname",
    "request.headrefname",
    "request.headrefoid",
    "request.isdraft",
    "request.mergeable",
    "request.mergedat",
    "request.mergestatestatus",
    "request.reviewdecision",
    "request.state",
    "resources-format.md",
    "resources.md",
    "result.status",
    "resume.md",
    "retrieved.name",
    "reviewer-prompt.md",
    "reviewthreads.nodes",
    "router.replace",
    "rubric.md",
    "runner-prompt.md",
    "runtime-forensics.md",
    "searchparams.get",
    "server.ts",
    "session-pickup.md",
    "session.tsx",
    "shipping.md",
    "show-me.ts",
    "skill-mechanics.md",
    "skill.md",
    "skill.ts",
    "spec.md",
    "state.vscdb.backup",
    "status.md",
    "store.ts",
    "stream.ts",
    "synthesizer.md",
    "template.sh",
    "tests.md",
    "thread.comments.nodes",
    "thread.id",
    "thread.isresolved",
    "tooling-reviewer.md",
    "trace-forensics.md",
    "transport.ts",
    "triage-labels.md",
    "tsconfig.json",
    "types.ts",
    "units.tsv",
    "user.email",
    "user.id",
    "user.name",
    "verdict.queue.map",
    "verify.md",
    "visual-parity.md",
    "worktree-audit.sh",
    "worktree-cleanup.md",
    "yarn.lock",
}
HOSTNAME_PATTERN = re.compile(
    r"\b[A-Za-z0-9-]{3,}(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,63}\b",
    re.IGNORECASE,
)
NON_HOST_SUFFIXES = {
    "date",
    "datetime",
    "dev",
    "dev-dependencies",
    "find",
    "html",
    "json",
    "jsonl",
    "md",
    "py",
    "requires-dev",
    "sqlite",
    "toml",
    "txt",
}
ID_VALUE_PATTERN = re.compile(r"^(?:[CDGUW][A-Z0-9]{8,}|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,})$")
SENSITIVE_NAMES = {
    "account",
    "account_alias",
    "account_id",
    "channel_id",
    "hostname",
    "password",
    "secret",
    "token",
    "user_id",
    "workspace_url",
}
SENSITIVE_VALUE_LABEL = "hardcoded credential, account alias, hostname, URL, or ID"
FIXTURE_ALLOW_MARKER = "# audit: allow-fixture"


def is_sensitive_name(name: str) -> bool:
    normalized = name.casefold()
    return normalized in SENSITIVE_NAMES or normalized.endswith(
        (
            "_account",
            "_alias",
            "_credential",
            "_host",
            "_hostname",
            "_id",
            "_key",
            "_password",
            "_secret",
            "_token",
            "_url",
        )
    )


def literal_string(value: ast.expr | None) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        left = literal_string(value.left)
        right = literal_string(value.right)
        if left is not None and right is not None:
            return left + right
    return None


def hardcoded_sensitive_value(
    names: list[str], value: ast.expr | None, *, allow_synthetic: bool = False
) -> bool:
    literal = literal_string(value)
    if literal is None and isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
        is_getenv = value.func.attr == "getenv"
        is_environ_get = (
            value.func.attr == "get"
            and isinstance(value.func.value, ast.Attribute)
            and value.func.value.attr == "environ"
        )
        if is_getenv or is_environ_get:
            fallback = value.args[1] if len(value.args) >= 2 else None
            if fallback is None:
                fallback = next(
                    (keyword.value for keyword in value.keywords if keyword.arg == "default"), None
                )
            literal = literal_string(fallback)
    if literal is None or not literal:
        return False
    sensitive_names = [name for name in names if is_sensitive_name(name)]
    if not sensitive_names:
        return False
    if allow_synthetic and literal.casefold().startswith(("example", "fake", "fixture", "test")):
        return False
    if all(name.casefold().endswith("_id") or name.casefold() == "id" for name in sensitive_names):
        return bool(ID_VALUE_PATTERN.fullmatch(literal))
    return True


def sensitive_violation(path: Path, line_number: int) -> str:
    return f"{path}:{line_number}: {SENSITIVE_VALUE_LABEL}"


def assigned_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Attribute):
        return [target.attr]
    if isinstance(target, (ast.List, ast.Tuple)):
        return [name for item in target.elts for name in assigned_names(item)]
    return []


def paired_assignments(target: ast.expr, value: ast.expr) -> list[tuple[list[str], ast.expr]]:
    if (
        isinstance(target, (ast.List, ast.Tuple))
        and isinstance(value, (ast.List, ast.Tuple))
        and len(target.elts) == len(value.elts)
    ):
        return [
            pair
            for target_item, value_item in zip(target.elts, value.elts, strict=True)
            for pair in paired_assignments(target_item, value_item)
        ]
    return [(assigned_names(target), value)]


def contains_hostname(value: str) -> bool:
    return any(
        match.group().rsplit(".", 1)[-1].casefold() not in NON_HOST_SUFFIXES
        for match in HOSTNAME_PATTERN.finditer(value)
    )


def contains_unapproved_url(value: str, *, allow_synthetic: bool) -> bool:
    for match in URL_PATTERN.finditer(value):
        url = match.group().rstrip(".,;:!?)]}")
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").casefold()
        if allow_synthetic and hostname.endswith(".invalid"):
            continue
        if hostname in PUBLIC_URL_HOSTS:
            continue
        if hostname == "github.com" and any(
            parsed.path == path or parsed.path.startswith(f"{path}/")
            for path in PUBLIC_GITHUB_PATHS
        ):
            continue
        return True
    return False


def contains_unapproved_vendor_url(value: str) -> bool:
    for match in URL_PATTERN.finditer(value):
        url = match.group().rstrip(".,;:!?)]}")
        hostname = (urlsplit(url).hostname or "").casefold()
        if hostname in VENDORED_PUBLIC_URL_HOSTS or hostname == "example.com":
            continue
        if hostname.endswith(".example.com"):
            continue
        return True
    return False


def contains_unapproved_vendor_hostname(value: str) -> bool:
    for match in HOSTNAME_PATTERN.finditer(value):
        hostname = match.group().casefold()
        if hostname in VENDORED_PUBLIC_BARE_HOSTS:
            continue
        return True
    return False


def find_violations(path: Path, *, allow_public_references: bool = False) -> list[str]:
    violations: list[str] = []
    try:
        display_path = path.relative_to(SOURCE_ROOT)
    except ValueError:
        display_path = path
    try:
        source = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return [f"{display_path}:1: text file is not valid UTF-8"]

    is_python = path.suffix == ".py"
    is_production_python = is_python and "tests" not in path.parts
    allow_synthetic = "tests" in path.parts
    source_lines = source.splitlines()
    fixture_markers_allowed = (
        path.resolve()
        == (SOURCE_ROOT / "scripts" / "tests" / "test_audit_public_source.py").resolve()
    )
    allowed_fixture_lines = {
        line_number
        for line_number, line in enumerate(source_lines, start=1)
        if fixture_markers_allowed and FIXTURE_ALLOW_MARKER in line
    }

    for line_number, line in enumerate(source_lines, start=1):
        if line_number in allowed_fixture_lines:
            continue
        url_is_unapproved = (
            contains_unapproved_vendor_url(line)
            if allow_public_references
            else contains_unapproved_url(line, allow_synthetic=allow_synthetic)
        )
        if url_is_unapproved:
            violations.append(f"{display_path}:{line_number}: hardcoded URL")
        for label, pattern in FORBIDDEN_PATTERNS.items():
            matches = pattern.finditer(line)
            if label == "email address" and allow_public_references:
                matches = (
                    match
                    for match in matches
                    if match.group().rsplit("@", 1)[-1].casefold() != "example.com"
                    and match.group().casefold() != "git@github.com"
                )
            if any(matches):
                violations.append(f"{display_path}:{line_number}: hardcoded {label}")
        if not is_python:
            if path.suffix in {"", ".md", ".txt", ".sh", ".bash"}:
                hostname_text = line
            else:
                quoted = re.findall(r'["\u0027]([^"\u0027]+)["\u0027]', line)
                hostname_text = " ".join(quoted)
            if allow_public_references:
                hostname_text = FORBIDDEN_PATTERNS["email address"].sub("", hostname_text)
            hostname_text = URL_PATTERN.sub("", hostname_text)
            hostname_is_unapproved = (
                contains_unapproved_vendor_hostname(hostname_text)
                if allow_public_references
                else contains_hostname(hostname_text)
            )
            if hostname_is_unapproved:
                violations.append(f"{display_path}:{line_number}: hardcoded hostname")

    if not is_python:
        return violations

    for node in ast.walk(ast.parse(source, filename=str(path))):
        if isinstance(node, ast.expr):
            literal = literal_string(node)
            if literal is not None:
                for label, pattern in FORBIDDEN_PATTERNS.items():
                    if pattern.search(literal):
                        violations.append(f"{display_path}:{node.lineno}: hardcoded {label}")
                url_is_unapproved = (
                    contains_unapproved_vendor_url(literal)
                    if allow_public_references
                    else contains_unapproved_url(literal, allow_synthetic=allow_synthetic)
                )
                if url_is_unapproved:
                    violations.append(f"{display_path}:{node.lineno}: hardcoded URL")
                if is_production_python and (
                    contains_unapproved_vendor_hostname(literal)
                    if allow_public_references
                    else contains_hostname(literal)
                ):
                    violations.append(f"{display_path}:{node.lineno}: hardcoded hostname")
                if ID_VALUE_PATTERN.fullmatch(literal):
                    violations.append(f"{display_path}:{node.lineno}: hardcoded ID")

        names: list[str] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            paired = isinstance(node.value, (ast.List, ast.Tuple)) and any(
                isinstance(target, (ast.List, ast.Tuple)) for target in node.targets
            )
            if paired:
                for target in node.targets:
                    for paired_names, paired_value in paired_assignments(target, node.value):
                        if hardcoded_sensitive_value(
                            paired_names, paired_value, allow_synthetic=allow_synthetic
                        ):
                            violations.append(sensitive_violation(display_path, node.lineno))
            else:
                names = [name for target in node.targets for name in assigned_names(target)]
                value = node.value
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            names = assigned_names(node.target)
            value = node.value
        elif isinstance(node, ast.keyword) and node.arg:
            names = [node.arg]
            value = node.value
        if hardcoded_sensitive_value(names, value, allow_synthetic=allow_synthetic):
            violations.append(sensitive_violation(display_path, node.lineno))

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = [*node.args.posonlyargs, *node.args.args]
            first_default = len(positional) - len(node.args.defaults)
            defaults = zip(positional[first_default:], node.args.defaults, strict=True)
            for argument, default in defaults:
                if hardcoded_sensitive_value(
                    [argument.arg], default, allow_synthetic=allow_synthetic
                ):
                    violations.append(sensitive_violation(display_path, node.lineno))
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
                if hardcoded_sensitive_value(
                    [argument.arg], default, allow_synthetic=allow_synthetic
                ):
                    violations.append(sensitive_violation(display_path, node.lineno))

        if isinstance(node, ast.Dict):
            for key, item in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and hardcoded_sensitive_value(
                        [key.value], item, allow_synthetic=allow_synthetic
                    )
                ):
                    violations.append(sensitive_violation(display_path, node.lineno))
    return [
        violation
        for violation in violations
        if not (
            (match := re.search(r":(\d+):", violation))
            and int(match.group(1)) in allowed_fixture_lines
        )
    ]


def public_paths(root: Path = SOURCE_ROOT) -> list[Path]:
    if (root / ".git").exists():
        # Commit hooks can point GIT_INDEX_FILE at this repository's staged index.
        # A nested temporary repository must use its own index and work tree.
        git_env = os.environ.copy()
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
            git_env.pop(name, None)
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            capture_output=True,
            check=True,
            env=git_env,
        )
        candidates = [root / path for path in result.stdout.decode().split("\0") if path]
    else:
        candidates = list(root.rglob("*"))

    paths: list[Path] = []
    for path in candidates:
        if not path.is_file() or path.resolve() == Path(__file__).resolve():
            continue
        if b"\0" in path.read_bytes():
            continue
        paths.append(path)
    return paths


def audit_paths(root: Path = SOURCE_ROOT) -> list[str]:
    lock_path = root / "skills-lock.json"
    locked_skills = set()
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        locked_skills = {
            re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
            for name, entry in lock.get("skills", {}).items()
            if entry.get("sourceType") == "github"
            and not entry.get("source", "").startswith("barbieri/")
        }

    violations = []
    for path in sorted(public_paths(root)):
        relative = path.relative_to(root)
        # Allow approved upstream examples, but scan other hosts and secrets.
        allow_public_references = (
            len(relative.parts) >= 4
            and relative.parts[:2] == (".agents", "skills")
            and relative.parts[2] in locked_skills
        )
        violations.extend(find_violations(path, allow_public_references=allow_public_references))
    return violations


def main() -> int:
    violations = audit_paths()
    if not violations:
        return 0
    print("\n".join(violations), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
