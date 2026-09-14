from paper_record.cli import main


def test_schema_command(capsys) -> None:
    assert main(["schema", "proposal"]) == 0
    assert '"operations"' in capsys.readouterr().out


def test_future_command_has_explicit_exit(capsys, tmp_path) -> None:
    assert main(["resolve", str(tmp_path), "UNRESOLVED-0001"]) == 2
    assert "not implemented yet" in capsys.readouterr().err


def test_whole_rejection_immediately_enters_item_review(monkeypatch, tmp_path) -> None:
    operation = {
        "item_id": "CLAIM-1",
        "action": "upsert",
        "target": "claims",
        "content": {"title": None, "body": "Alpha", "value": None, "unit": None},
        "provenance": [],
        "read_status": "TEXT_READ",
        "evidence_status": "NOT_CHECKED",
    }
    envelope = {
        "proposal": {
            "reading": {"purpose": "test", "result": "test"},
            "operations": [operation],
            "evidence_requests": [],
        }
    }
    captured = {}
    answers = iter(["n", "a", "y"])
    monkeypatch.setattr("paper_record.cli.load_proposal", lambda paper, read_id: (tmp_path / "proposal.json", envelope))
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    def fake_apply(paper, read_id, decisions):
        captured["decisions"] = decisions
        return tmp_path / "review.json"

    monkeypatch.setattr("paper_record.cli.apply_review", fake_apply)
    assert main(["review", str(tmp_path), "--read-id", "READ-0001"]) == 0
    assert captured["decisions"] == [
        {"item_id": "CLAIM-1", "decision": "ACCEPTED", "feedback": None}
    ]
