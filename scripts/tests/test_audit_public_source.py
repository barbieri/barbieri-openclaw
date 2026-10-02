import json
import subprocess
from pathlib import Path

import pytest

from scripts.audit_public_source import audit_paths, find_violations, public_paths


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ('value = "https://service.invalid"', "URL"),
        ('value = "person@example.invalid"', "email address"),  # audit: allow-fixture
        ('value = "/home/person/config"', "user home path"),  # audit: allow-fixture
        (r'value = "C:\\Users\\person\\config"', "user home path"),  # audit: allow-fixture
        ('value = "xoxb-1234567890abcdef"', "secret token"),  # audit: allow-fixture
        ('value = "Bearer abc.def.ghi"', "secret token"),  # audit: allow-fixture
        ('value = "bearer abc.def.ghi"', "secret token"),  # audit: allow-fixture
        ('value = "xapp-1234567890abcdef"', "secret token"),  # audit: allow-fixture
        ('value = "service.corp.invalid"', "hostname"),
        ('value = "private.COMPANY.COM"', "hostname"),
        ('value = "private.example.finance"', "hostname"),
        ('value = "company.test"', "hostname"),
        ('API_HOST = "company.test"', "hostname"),
        ('value = "C0123456789"', "hardcoded ID"),  # audit: allow-fixture
        ('account = "personal"', "account alias"),
        ('self.account = "personal"', "account alias"),
        ('account = "per" + "sonal"', "account alias"),
        ('if token := "hunter2": ...', "credential"),
        ('account, token = ("personal", "hunter2")', "credential"),
        ('token = os.getenv("TOKEN", "hunter2")', "credential"),
        ('token = os.getenv("TOKEN", default="hunter2")', "credential"),
        ('token = os.environ.get("TOKEN", "hunter2")', "credential"),
        ('PASSWORD = "hunter2"', "credential"),
        ('def connect(account="private"): pass', "account alias"),
        ('config = {"channel_id": "C0123456789"}', "account alias"),  # audit: allow-fixture
    ],
)
def test_finds_private_production_values(tmp_path: Path, source: str, label: str) -> None:
    source_path = tmp_path / "source.py"
    source_path.write_text(source, encoding="utf-8")

    assert any(label in violation for violation in find_violations(source_path))


def test_scans_documentation_without_python_parsing(tmp_path: Path) -> None:
    readme_path = tmp_path / "README.md"
    readme_path.write_text("Connect to db.company.test.\n", encoding="utf-8")

    assert any("hostname" in violation for violation in find_violations(readme_path))


@pytest.mark.parametrize(
    "source",
    [
        "slack-summary --channel C0123456789",  # audit: allow-fixture
        "Workspace id: 01234567-89ab-cdef-0123-456789abcdef",  # audit: allow-fixture
    ],
)
def test_finds_unquoted_documentation_ids(tmp_path: Path, source: str) -> None:
    readme_path = tmp_path / "README.md"
    readme_path.write_text(source, encoding="utf-8")

    assert any("hardcoded ID" in violation for violation in find_violations(readme_path))


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ('endpoint = "https" + "://" + "10.0.0.1/private"', "URL"),
        ('contact = "person" + "@" + "private" + ".com"', "email address"),
    ],
)
def test_reconstructs_concatenated_literals(tmp_path: Path, source: str, label: str) -> None:
    source_path = tmp_path / "source.py"
    source_path.write_text(source, encoding="utf-8")

    assert any(label in violation for violation in find_violations(source_path))


def test_reconstructs_concatenated_ids(tmp_path: Path) -> None:
    source_path = tmp_path / "source.py"
    source_path.write_text('value = "C0123" + "456789"', encoding="utf-8")

    assert any("hardcoded ID" in violation for violation in find_violations(source_path))


def test_sensitive_assignment_reports_once(tmp_path: Path) -> None:
    source_path = tmp_path / "source.py"
    source_path.write_text('token = "hunter2"', encoding="utf-8")

    violations = find_violations(source_path)

    assert violations.count(next(item for item in violations if "credential" in item)) == 1


def test_public_paths_include_root_policy_documentation(tmp_path: Path) -> None:
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text("# Policy\n", encoding="utf-8")
    nested_path = tmp_path / "skills" / "demo" / "examples" / "INSTRUCTIONS.md"
    nested_path.parent.mkdir(parents=True)
    nested_path.write_text("# Instructions\n", encoding="utf-8")
    config_path = tmp_path / "pyproject.toml"
    config_path.write_text('[project]\nname = "example"\n', encoding="utf-8")
    fixture_path = tmp_path / "tests" / "fixture.json"
    fixture_path.parent.mkdir()
    fixture_path.write_text('{"value": "example"}\n', encoding="utf-8")

    assert agents_path in public_paths(tmp_path)
    assert nested_path in public_paths(tmp_path)
    assert config_path in public_paths(tmp_path)
    assert fixture_path in public_paths(tmp_path)


def test_public_paths_skip_binary_files(tmp_path: Path) -> None:
    binary_path = tmp_path / "image.bin"
    binary_path.write_bytes(b"image\0data")

    assert binary_path not in public_paths(tmp_path)


def test_invalid_utf8_text_is_a_violation(tmp_path: Path) -> None:
    text_path = tmp_path / "configuration.toml"
    text_path.write_bytes(b'name = "\xff"\n')

    assert any("not valid UTF-8" in item for item in find_violations(text_path))


def test_fixture_marker_does_not_exempt_production_files(tmp_path: Path) -> None:
    source_path = tmp_path / "production.py"
    source_path.write_text(
        'token = "hunter2"  # audit: allow-fixture\n',
        encoding="utf-8",
    )

    assert any("credential" in item for item in find_violations(source_path))


def test_synthetic_prefix_does_not_exempt_production_values(tmp_path: Path) -> None:
    source_path = tmp_path / "production.py"
    source_path.write_text('token = "test-secret"\n', encoding="utf-8")

    assert any("credential" in item for item in find_violations(source_path))


@pytest.mark.parametrize("suffix", [".md", ".toml"])
def test_private_urls_are_rejected_in_repository_text(tmp_path: Path, suffix: str) -> None:
    source_path = tmp_path / f"configuration{suffix}"
    source_path.write_text(
        'endpoint = "https://private.company.test/api"\n',  # audit: allow-fixture
        encoding="utf-8",
    )

    assert any("hardcoded URL" in item for item in find_violations(source_path))


def test_public_paths_follow_git_ignore_without_skipping_dot_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A commit hook can export pointers to the parent repository. Initialize
    # the fixture independently, then verify the scanner ignores such pointers.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX"):
        monkeypatch.delenv(name, raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("node_modules/\nreports/\n", encoding="utf-8")
    security_path = tmp_path / ".github" / "SECURITY.md"
    security_path.parent.mkdir()
    security_path.write_text("# Security\n", encoding="utf-8")
    ignored_path = tmp_path / "node_modules" / "package" / "README.md"
    ignored_path.parent.mkdir(parents=True)
    ignored_path.write_text("# Dependency\n", encoding="utf-8")

    monkeypatch.setenv("GIT_DIR", str(tmp_path / "not-a-repository"))
    paths = public_paths(tmp_path)

    assert security_path in paths
    assert ignored_path not in paths


def test_locked_skill_public_references_do_not_hide_sensitive_values(tmp_path: Path) -> None:
    (tmp_path / "skills-lock.json").write_text(
        json.dumps({"skills": {"demo": {"source": "mattpocock/skills", "sourceType": "github"}}}),
        encoding="utf-8",
    )
    skill = tmp_path / ".agents" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        (
            "https://docs.example.com\n"  # audit: allow-fixture
            "git@github.com\n"  # audit: allow-fixture
            "person@example.com\n"  # audit: allow-fixture
            "person@private.test\n"  # audit: allow-fixture
            "person@github.com\n"  # audit: allow-fixture
            "/home/person/config\n"  # audit: allow-fixture
            "https://private-host.example.net/secret\n"  # audit: allow-fixture
            "internal.example.net\n"  # audit: allow-fixture
            "private.company.finance\n"  # audit: allow-fixture
        ),
        encoding="utf-8",
    )
    unlisted = tmp_path / ".agents" / "skills" / "unlisted" / "SKILL.md"
    unlisted.parent.mkdir(parents=True)
    unlisted.write_text("https://docs.example.com\n", encoding="utf-8")  # audit: allow-fixture

    violations = audit_paths(tmp_path)

    assert sum("hardcoded URL" in item for item in violations) == 2
    assert sum("hardcoded hostname" in item for item in violations) == 2
    assert sum("hardcoded email address" in item for item in violations) == 2
    assert any("hardcoded user home path" in item for item in violations)


def test_owned_locked_skill_keeps_full_url_scan(tmp_path: Path) -> None:
    (tmp_path / "skills-lock.json").write_text(
        json.dumps(
            {
                "skills": {
                    "owned": {
                        "source": "barbieri/barbieri-playground",
                        "sourceType": "github",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    skill = tmp_path / ".agents" / "skills" / "owned" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("https://private-host.example.net\n", encoding="utf-8")  # audit: allow-fixture

    assert any("hardcoded URL" in item for item in audit_paths(tmp_path))


@pytest.mark.parametrize(
    ("filename", "source"),
    [
        ("SKILL.md", "```sh\nAPI_HOST=private.company.finance\n```\n"),  # audit: allow-fixture
        (
            "SKILL.md",
            "Set `API_HOST=private.company.finance` before running.\n",  # audit: allow-fixture
        ),
        ("script.sh", "curl private.company.finance\n"),  # audit: allow-fixture
        ("SKILL.md", "private.company.dev\n"),  # audit: allow-fixture
        ("SKILL.md", "private.company.fr\n"),  # audit: allow-fixture
        ("SKILL.md", "private.company.email\n"),  # audit: allow-fixture
        ("SKILL.md", "private.company.name\n"),  # audit: allow-fixture
        ("SKILL.md", "vault.home\n"),  # audit: allow-fixture
        ("SKILL.md", "nas.mydomain\n"),  # audit: allow-fixture
        ("script.sh", "curl vault.home\n"),  # audit: allow-fixture
        (
            "SKILL.md",
            "https://github.com/foo and vault.home\n",  # audit: allow-fixture
        ),
    ],
)
def test_locked_skill_detects_private_bare_hosts_in_code_and_real_tlds(
    tmp_path: Path, filename: str, source: str
) -> None:
    (tmp_path / "skills-lock.json").write_text(
        json.dumps({"skills": {"demo": {"source": "mattpocock/skills", "sourceType": "github"}}}),
        encoding="utf-8",
    )
    skill_file = tmp_path / ".agents" / "skills" / "demo" / filename
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(source, encoding="utf-8")

    assert any("hardcoded hostname" in item for item in audit_paths(tmp_path))
