from paper_record.canonical import ensure_canonical_scaffold


def test_scaffold_is_created_once_and_has_no_interpretation(tmp_path) -> None:
    assert ensure_canonical_scaffold(tmp_path)
    text = (tmp_path / "03_canonical.md").read_text(encoding="utf-8")
    assert "reading_status: NOT_READ" in text
    assert "# Reading Ledger" in text
    assert not ensure_canonical_scaffold(tmp_path)
