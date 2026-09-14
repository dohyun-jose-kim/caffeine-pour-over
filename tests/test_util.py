import json
from pathlib import Path

import pytest

from paper_record.audit import AuditLog
from paper_record.util import atomic_write_text, ensure_within, next_numbered_id, slugify


def test_slug_and_numbered_ids() -> None:
    assert slugify("Smith 2026.pdf") == "smith-2026.pdf"
    assert next_numbered_id(["READ-0001", "READ-0009"], "READ") == "READ-0010"


def test_path_containment(tmp_path: Path) -> None:
    assert ensure_within(tmp_path, tmp_path / "paper.pdf") == tmp_path / "paper.pdf"
    with pytest.raises(ValueError, match="escapes"):
        ensure_within(tmp_path, tmp_path.parent / "outside.pdf")


def test_atomic_write_replaces_complete_file(tmp_path: Path) -> None:
    path = tmp_path / "record.md"
    path.write_text("old", encoding="utf-8")
    atomic_write_text(path, "new\n")
    assert path.read_text(encoding="utf-8") == "new\n"


def test_audit_log_is_jsonl_and_separates_error(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "paper", "doctor")
    log.event("COMMAND_FAILED", "FAILED", stage="probe", error="safe message")
    record = json.loads(log.path.read_text(encoding="utf-8"))
    assert record["error"] == "safe message"
    assert record["context"] == {"stage": "probe"}
