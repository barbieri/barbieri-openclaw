import json
import subprocess
import sys
from pathlib import Path

import one_click_unsubscribe as unsubscribe_http

MODULE = Path(__file__).parents[1] / "src" / "one_click_unsubscribe" / "__init__.py"


def test_cli_dry_run_validates_without_posting(monkeypatch, capsys):
    from io import BytesIO

    monkeypatch.setattr(unsubscribe_http, "_validate_https_url", lambda _url: None)
    monkeypatch.setattr(
        unsubscribe_http,
        "post_one_click",
        lambda _url: (_ for _ in ()).throw(AssertionError("dry-run posted")),
    )

    old_stdin = unsubscribe_http.sys.stdin
    unsubscribe_http.sys.stdin = type(
        "Input", (), {"buffer": BytesIO(b"https://example.invalid/u")}
    )()
    try:
        assert unsubscribe_http.main([]) == 0
    finally:
        unsubscribe_http.sys.stdin = old_stdin
    assert json.loads(capsys.readouterr().out) == {"status": "dry_run"}


def test_cli_execute_uses_existing_post_function(monkeypatch, capsys):
    from io import BytesIO

    calls = []
    monkeypatch.setattr(unsubscribe_http, "_validate_https_url", lambda _url: None)
    monkeypatch.setattr(unsubscribe_http, "post_one_click", calls.append)
    old_stdin = unsubscribe_http.sys.stdin
    unsubscribe_http.sys.stdin = type(
        "Input", (), {"buffer": BytesIO(b"https://example.invalid/u")}
    )()

    try:
        assert unsubscribe_http.main(["--execute"]) == 0
    finally:
        unsubscribe_http.sys.stdin = old_stdin
    assert calls == ["https://example.invalid/u"]
    assert json.loads(capsys.readouterr().out) == {"status": "unsubscribed"}


def test_cli_rejects_private_target(capsys):
    from io import BytesIO

    old_stdin = unsubscribe_http.sys.stdin
    unsubscribe_http.sys.stdin = type("Input", (), {"buffer": BytesIO(b"https://127.0.0.1/x")})()
    try:
        assert unsubscribe_http.main([]) == 1
    finally:
        unsubscribe_http.sys.stdin = old_stdin
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "error": "URL validation or unsubscribe request failed",
        "status": "failed",
    }
    assert "127.0.0.1" not in output.out + output.err


def test_cli_transport_error_does_not_expose_url(capsys, monkeypatch):
    secret_url = "https://example.invalid/path?token=private"
    monkeypatch.setattr(unsubscribe_http, "_validate_https_url", lambda _url: None)
    monkeypatch.setattr(
        unsubscribe_http,
        "post_one_click",
        lambda _url: (_ for _ in ()).throw(OSError(secret_url)),
    )
    from io import BytesIO

    old_stdin = unsubscribe_http.sys.stdin
    unsubscribe_http.sys.stdin = type("Input", (), {"buffer": BytesIO(secret_url.encode())})()
    try:
        assert unsubscribe_http.main(["--execute"]) == 1
    finally:
        unsubscribe_http.sys.stdin = old_stdin
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "error": "URL validation or unsubscribe request failed",
        "status": "failed",
    }
    assert secret_url not in output.out + output.err


def test_standalone_cli_help_dry_run_and_invalid_input():
    help_result = subprocess.run(
        [sys.executable, str(MODULE), "--help"], capture_output=True, text=True, check=False
    )
    assert help_result.returncode == 0
    assert "--execute" in help_result.stdout

    dry_run = subprocess.run(
        [sys.executable, str(MODULE)],
        input="https://192.0.0.9/unsubscribe\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert dry_run.returncode == 0
    assert json.loads(dry_run.stdout) == {"status": "dry_run"}

    invalid = subprocess.run(
        [sys.executable, str(MODULE)],
        input="".join(("http:", "/", "/invalid.example/private-token\n")),
        capture_output=True,
        text=True,
        check=False,
    )
    assert invalid.returncode == 1
    assert json.loads(invalid.stdout) == {
        "error": "URL validation or unsubscribe request failed",
        "status": "failed",
    }
    assert "private-token" not in invalid.stdout + invalid.stderr
