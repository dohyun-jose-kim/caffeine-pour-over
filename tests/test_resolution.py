from pathlib import Path

import pytest

from paper_record.resolution import resolve_unresolved


def test_resolution_requires_explicit_visual_evidence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit"):
        resolve_unresolved(tmp_path, "UNRESOLVED-1", pages=None, assets=[])


def test_resolution_focuses_existing_item(monkeypatch, tmp_path: Path) -> None:
    state = {
        "unresolved": [
            {
                "item_id": "UNRESOLVED-1",
                "content": {"body": "conflict"},
            }
        ]
    }
    captured = {}
    monkeypatch.setattr("paper_record.resolution.load_canonical", lambda path: (state, ""))

    def fake_read(paper_dir, **kwargs):
        captured.update(kwargs)
        return "READ-0002", Path("proposal.json")

    monkeypatch.setattr("paper_record.resolution.read_paper", fake_read)
    read_id, _ = resolve_unresolved(
        tmp_path, "UNRESOLVED-1", pages="2", assets=[], provider_name="codex"
    )
    assert read_id == "READ-0002"
    assert "Resolve only canonical unresolved item UNRESOLVED-1" in captured["purpose"]
    assert captured["pages"] == "2"
