"""Guard the generated Gustavo Style include against canonical drift.

The canonical design system lives in `barbieri-playground/design/DESIGN.md` and
is turned into `style.py` by `scripts/export_gustavo_style.py`. Without this
check a canonical edit could silently leave the calendar email behind.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EXPORTER = REPO_ROOT / "scripts" / "export_gustavo_style.py"
CANONICAL = REPO_ROOT.parent / "barbieri-playground" / "design" / "DESIGN.md"
GENERATED = REPO_ROOT / "skills" / "daily-calendar" / "src" / "daily_calendar" / "style.py"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_gustavo_style", EXPORTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_style_matches_canonical_design() -> None:
    if not CANONICAL.exists():
        # The canonical document is a sibling clone; skip rather than fail CI on
        # a checkout that does not have it.
        import pytest

        pytest.skip(f"canonical design document not present at {CANONICAL}")

    exporter = _load_exporter()
    css, _families, _light = exporter.export(CANONICAL.read_text())
    expected = (
        '"""Generated Gustavo Style include. See design/README.md."""\n\n'
        'CSS = """\n' + css + '"""\n'
    )
    assert GENERATED.read_text() == expected, (
        "skills/daily-calendar/src/daily_calendar/style.py is out of date with "
        "the canonical DESIGN.md; re-run scripts/export_gustavo_style.py"
    )
