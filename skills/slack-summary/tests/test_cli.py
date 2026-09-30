from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from slack_summary.cleanup import TextCleaner, is_valid_cpf
from slack_summary.cli import build_parser, main
from slack_summary.references import slack_href
from slack_summary.slacrawl import Author, BotStatus, SourceMessage, SourceThread
from slack_summary.transcript import PreparedMessage, iter_thread_records


def fixture_email(local: str) -> str:
    return f"{local}@example.invalid"


def write_db(path: Path) -> None:
    dev_email = fixture_email("dev")
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE messages (
              channel_id TEXT,
              ts TEXT,
              workspace_id TEXT,
              user_id TEXT,
              subtype TEXT,
              text TEXT,
              thread_ts TEXT,
              deleted_ts TEXT,
              raw_json TEXT
            );
            CREATE TABLE users (
              id TEXT,
              workspace_id TEXT,
              name TEXT,
              real_name TEXT,
              display_name TEXT,
              is_bot INTEGER,
              raw_json TEXT
            );
            INSERT INTO users VALUES
              ('U1', 'T1', 'ana', 'Ana Example', 'Ana', 0, '{}'),
              ('U2', 'T1', 'bia', 'Bia Example', '', 0, '{}'),
              ('B1', 'T1', 'deploybot', 'Deploy Bot', '', 1, '{}');
            INSERT INTO messages VALUES
              ('C1', '1703977200.000001', 'T1', 'U1', NULL,
               'Earlier root from Ana', NULL, NULL, '{}'),
              ('C1', '1704067200.000001', 'T1', 'U1', NULL,
               'Decision: pause the deploy', NULL, NULL, '{}'),
              ('C1', '1704067265.000001', 'T1', 'U2', NULL,
               'I will inspect it', '1704067200.000001', NULL, '{}'),
              ('C1', '1704067325.000001', 'T1', 'B1', 'bot_message',
               'Automated build passed', '1704067200.000001', NULL,
               '{"bot_id":"B1"}'),
              ('C1', '1704067385.000001', 'T1', 'U2', NULL,
               'Contact FIXTURE_EMAIL or +55 11 91234-5678; CPF 123.456.789-09',
               '1703977200.000001', NULL, '{}'),
              ('C1', '1704067445.000001', 'T1', 'U2', NULL,
               'FIXTURE_EMAIL, +55 11 91234-5678, 123.456.789-09',
               NULL, NULL, '{}'),
              ('C1', '1704067505.000001', 'T1', 'B1', 'bot_message',
               'Standalone automation', NULL, NULL, '{"bot_id":"B1"}'),
              ('C1', '1704067565.000001', 'T1', 'U1', NULL,
               'Deleted private text', NULL, '1704067600', '{}'),
              ('C2', '1704067200.000002', 'T1', 'U1', NULL,
               'Other channel', NULL, NULL, '{}');
            """.replace("FIXTURE_EMAIL", dev_email)
        )


def run_cli(db_path: Path, *extra: str) -> int:
    return main(
        [
            "--database",
            str(db_path),
            "--channel",
            "C1",
            "--workspace-url",
            "https://slack.example.invalid/",
            "--timezone",
            "America/Sao_Paulo",
            "--start",
            "2023-12-31",
            "--end",
            "2024-01-01",
            *extra,
        ]
    )


def output_records(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_channel_rejects_empty_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_SUMMARY_CHANNEL", raising=False)
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "--database",
                str(tmp_path / "fixture.db"),
                "--channel",
                " ",
                "--workspace-url",
                "https://slack.example.invalid",
                "--timezone",
                "UTC",
            ]
        )


def test_threads_are_grouped_linked_localized_and_bots_are_filtered(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)

    assert run_cli(db_path) == 0
    records = output_records(capsys)

    decision = next(
        record
        for record in records
        if record["thread"]["root"] and "Decision" in record["thread"]["root"]["text"]
    )
    thread = decision["thread"]
    assert thread["href"] == "https://slack.example.invalid/archives/C1/p1704067200000001"
    assert thread["root"]["timestamp"] == "2023-12-31T21:00-03:00"
    assert thread["root"]["author"] == {"id": "U1", "name": "Ana"}
    assert [reply["text"] for reply in thread["replies"]] == ["I will inspect it"]
    assert thread["replies"][0]["href"] == (
        "https://slack.example.invalid/archives/C1/p1704067265000001?thread_ts=1704067200.000001"
    )
    serialized = json.dumps(records)
    assert "Automated build passed" not in serialized
    assert "Standalone automation" not in serialized
    assert "Deleted private text" not in serialized


def test_reply_fetches_out_of_window_root_and_only_text_is_cleaned(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)

    assert run_cli(db_path) == 0
    records = output_records(capsys)
    thread = next(
        record["thread"]
        for record in records
        if record["thread"]["href"].endswith("p1703977200000001")
    )

    assert thread["root"]["text"] == "Earlier root from Ana"
    assert thread["root"]["context_only"] is True
    assert thread["replies"][0]["text"] == "Contact [EMAIL] or [PHONE]; CPF [CPF]"
    assert thread["replies"][0]["author"] == {"id": "U2", "name": "Bia Example"}
    assert thread["root_omitted_reason"] is None


def test_fully_redacted_message_is_omitted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)

    assert run_cli(db_path) == 0
    serialized = json.dumps(output_records(capsys))
    assert "1704067445" not in serialized
    assert fixture_email("dev") not in serialized
    assert "91234-5678" not in serialized
    assert "123.456.789-09" not in serialized


def test_include_bots_restores_bot_messages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)

    assert run_cli(db_path, "--include-bots") == 0
    serialized = json.dumps(output_records(capsys))
    assert "Automated build passed" in serialized
    assert "Standalone automation" in serialized


def test_default_bot_filter_retains_unknown_authorship(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "minimal.db"
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE messages (channel_id TEXT, ts TEXT, text TEXT);
            INSERT INTO messages VALUES ('C1', '1704067200', 'minimal schema');
            """
        )

    assert run_cli(db_path) == 0
    [record] = output_records(capsys)
    assert record["thread"]["root"]["text"] == "minimal schema"


def test_limit_keeps_whole_newest_conversation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)

    assert run_cli(db_path, "--limit", "1") == 0
    [record] = output_records(capsys)
    thread = record["thread"]
    assert len(thread["replies"]) == 1


def test_limit_counts_a_complete_thread_as_one_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)

    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            INSERT INTO messages VALUES
              ('C1', '1704067490.000001', 'T1', 'U1', NULL,
               'Newest root', NULL, NULL, '{}')
            """
        )
        db.execute(
            """
            INSERT INTO messages VALUES
              ('C1', '1704067495.000001', 'T1', 'U2', NULL,
               'Newest reply', '1704067490.000001', NULL, '{}')
            """
        )

    assert run_cli(db_path, "--limit", "1") == 0
    [record] = output_records(capsys)
    assert record["thread"]["root"] is not None
    assert len(record["thread"]["replies"]) == 1


def test_redacted_root_is_omitted_but_thread_and_reply_remain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE messages SET text = ? WHERE ts = ?",
            (fixture_email("owner"), "1704067200.000001"),
        )

    assert run_cli(db_path) == 0
    records = output_records(capsys)
    thread = next(
        record["thread"]
        for record in records
        if record["thread"]["href"].endswith("p1704067200000001")
    )
    assert thread["root"] is None
    assert thread["root_omitted_reason"] == "redacted"
    assert [reply["text"] for reply in thread["replies"]] == ["I will inspect it"]


def test_filtered_bot_root_has_an_explicit_omission_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE messages SET user_id = 'B1', subtype = 'bot_message' WHERE ts = ?",
            ("1704067200.000001",),
        )

    assert run_cli(db_path) == 0
    records = output_records(capsys)
    thread = next(
        record["thread"]
        for record in records
        if record["thread"]["href"].endswith("p1704067200000001")
    )
    assert thread["root"] is None
    assert thread["root_omitted_reason"] == "filtered_bot"
    assert [reply["text"] for reply in thread["replies"]] == ["I will inspect it"]


def test_output_orders_threads_by_root_context_not_latest_reply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)

    assert run_cli(db_path) == 0
    hrefs = [record["thread"]["href"] for record in output_records(capsys)]
    assert hrefs.index("https://slack.example.invalid/archives/C1/p1703977200000001") < hrefs.index(
        "https://slack.example.invalid/archives/C1/p1704067200000001"
    )


def test_slack_href_treats_self_thread_timestamp_as_root() -> None:
    assert slack_href("https://slack.example.invalid/", "C1", "1000.000001", "1000.000001") == (
        "https://slack.example.invalid/archives/C1/p1000000001"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("123.456.789-09", True),
        ("12345678909", True),
        ("111.111.111-11", False),
        ("123.456.789-00", False),
    ],
)
def test_cpf_validation(value: str, expected: bool) -> None:
    assert is_valid_cpf(value) is expected


def test_cleaner_preserves_names_and_unsupported_pii() -> None:
    cleaner = TextCleaner.with_default_secret_scanner()
    text = f"Ana lives at Example Street, IP 192.0.2.10, email {fixture_email('ana')}"
    assert cleaner.clean(text) == "Ana lives at Example Street, IP 192.0.2.10, email [EMAIL]"


def test_cleaner_redacts_detected_secret() -> None:
    cleaner = TextCleaner.with_default_secret_scanner()
    # Synthetic token with a provider prefix; never accepted by a real service.
    token = "".join(("ghp_", "a" * 36))
    assert cleaner.clean(f"Rotate {token} today") == "Rotate [SECRET] today"


def test_secret_redaction_preserves_regex_context() -> None:
    cleaner = TextCleaner.with_default_secret_scanner()
    synthetic_key = "a" * 40
    text = f'Keep this context: aws password "{synthetic_key}" after'
    assert cleaner.clean(text) == 'Keep this context: aws password "[SECRET]" after'


def test_aws_access_key_without_capture_group_is_redacted() -> None:
    cleaner = TextCleaner.with_default_secret_scanner()
    synthetic_key = "AKIA" + "A" * 16
    assert cleaner.clean(f"Rotate {synthetic_key} today") == "Rotate [SECRET] today"


@pytest.mark.parametrize("token", ["glcbt-" + "A" * 25, "glcbt-ab_" + "A" * 25])
def test_gitlab_secret_redaction_covers_the_complete_token(token: str) -> None:
    cleaner = TextCleaner.with_default_secret_scanner()
    assert cleaner.clean(f"Rotate {token} today") == "Rotate [SECRET] today"


def test_npm_secret_redaction_preserves_trailing_context() -> None:
    cleaner = TextCleaner.with_default_secret_scanner()
    token = "npm_" + "a" * 36
    text = f"//registry.example.invalid/:_authToken={token} trailing prose"
    assert cleaner.clean(text) == "//registry.example.invalid/:_authToken=[SECRET] trailing prose"


def test_cleaner_omits_messages_containing_only_redacted_field_labels() -> None:
    cleaner = TextCleaner.with_default_secret_scanner()
    text = f"E-mail: {fixture_email('ana')}; CPF: 123.456.789-09"
    assert cleaner.clean(text) is None


def test_thread_limit_is_lazy_and_redacted_threads_do_not_count() -> None:
    fixture_base = "https://slack.example.invalid"
    closed = False

    def source_threads():
        nonlocal closed
        try:
            yield SourceThread(
                "1000.000001",
                iter(
                    [
                        SourceMessage(
                            "C1",
                            "1000.000001",
                            None,
                            Author("U1", "Ana Example"),
                            fixture_email("only"),
                            BotStatus.HUMAN,
                            True,
                        )
                    ]
                ),
            )
            yield SourceThread(
                "1001.000001",
                iter(
                    [
                        SourceMessage(
                            "C1",
                            "1001.000001",
                            None,
                            Author("U2", "Bia Example"),
                            "Useful update",
                            BotStatus.UNKNOWN,
                            True,
                        )
                    ]
                ),
            )
            raise AssertionError("the pipeline pulled a thread after reaching its limit")
        finally:
            closed = True

    records = list(
        iter_thread_records(
            source_threads(),
            cleaner=TextCleaner.with_default_secret_scanner(),
            include_bots=False,
            limit=1,
            workspace_url=fixture_base,
            timezone=__import__("zoneinfo").ZoneInfo("UTC"),
        )
    )
    assert len(records) == 1
    root = records[0]["thread"]["root"]
    assert isinstance(root, dict)
    assert root["author"] == {"id": "U2", "name": "Bia Example"}
    assert closed is True


def test_model_facing_message_cannot_retain_a_source_message() -> None:
    assert "source" not in PreparedMessage.__dataclass_fields__


def test_workspace_url_rejects_paths() -> None:
    with pytest.raises(ValueError, match="without credentials, path"):
        slack_href("https://slack.example.invalid/team", "C1", "1000.000001", None)


def test_invalid_window_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "slack.db"
    write_db(db_path)

    assert run_cli(db_path, "--start", "2024-01-02", "--end", "2024-01-01") == 1
    assert "--start must be before --end" in capsys.readouterr().err
