import json
import subprocess
from pathlib import Path

from paper_record.providers import ClaudeProvider, CodexProvider
from paper_record.schema import PROPOSAL_SCHEMA


def test_codex_and_claude_normalize_to_same_proposal(monkeypatch, tmp_path: Path) -> None:
    expected = {
        "reading": {"purpose": "Initial", "result": "Reviewed both records"},
        "operations": [],
        "evidence_requests": [],
    }
    commands: list[list[str]] = []

    monkeypatch.setattr("paper_record.providers._require_command", lambda name: name)
    monkeypatch.setattr("paper_record.providers._version", lambda command: "mock 1.0")

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "codex":
            output = Path(command[command.index("-o") + 1])
            output.write_text(json.dumps(expected), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")
        envelope = {"structured_output": expected}
        return subprocess.CompletedProcess(command, 0, json.dumps(envelope), "")

    monkeypatch.setattr("paper_record.providers.subprocess.run", fake_run)

    codex = CodexProvider().run(
        prompt="read", schema=PROPOSAL_SCHEMA, paper_dir=tmp_path, images=[], model=None
    )
    claude = ClaudeProvider().run(
        prompt="read", schema=PROPOSAL_SCHEMA, paper_dir=tmp_path, images=[], model=None
    )

    assert codex.proposal == claude.proposal == expected
    assert "read-only" in commands[0]
    assert "--ephemeral" in commands[0]
    assert "--no-session-persistence" in commands[1]
    assert "dontAsk" in commands[1]
