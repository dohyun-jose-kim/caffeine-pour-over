from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderResult:
    proposal: dict[str, Any]
    provider: str
    requested_model: str | None
    cli_version: str


class Provider(Protocol):
    name: str

    def run(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        paper_dir: Path,
        images: list[Path],
        model: str | None,
    ) -> ProviderResult: ...


class CodexProvider:
    name = "codex"

    def run(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        paper_dir: Path,
        images: list[Path],
        model: str | None,
    ) -> ProviderResult:
        executable = _require_command("codex")
        version = _version([executable, "--version"])
        with tempfile.TemporaryDirectory(prefix="paper-record-codex-") as temporary:
            schema_path = Path(temporary) / "proposal.schema.json"
            output_path = Path(temporary) / "proposal.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                executable,
                "exec",
                "-C",
                str(paper_dir),
                "-s",
                "read-only",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
            ]
            if model:
                command.extend(("--model", model))
            for image in images:
                command.extend(("--image", str(image)))
            command.append("-")
            completed = subprocess.run(
                command, input=prompt, text=True, capture_output=True, check=False
            )
            if completed.returncode:
                raise RuntimeError(_failure("Codex", completed))
            try:
                proposal = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError("Codex did not produce a valid JSON proposal") from error
        return ProviderResult(proposal, self.name, model, version)


class ClaudeProvider:
    name = "claude"

    def run(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        paper_dir: Path,
        images: list[Path],
        model: str | None,
    ) -> ProviderResult:
        executable = _require_command("claude")
        version = _version([executable, "--version"])
        command = [
            executable,
            "--print",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema, separators=(",", ":")),
            "--permission-mode",
            "dontAsk",
            "--tools",
            "Read",
            "--no-session-persistence",
        ]
        if model:
            command.extend(("--model", model))
        visual_instruction = "\n".join(f"- {path}" for path in images) or "- none"
        completed = subprocess.run(
            command,
            input=prompt + "\n\nVisual files available through Read:\n" + visual_instruction,
            text=True,
            capture_output=True,
            check=False,
            cwd=paper_dir,
        )
        if completed.returncode:
            raise RuntimeError(_failure("Claude", completed))
        try:
            envelope = json.loads(completed.stdout)
            proposal = envelope.get("structured_output")
            if proposal is None and isinstance(envelope.get("result"), str):
                proposal = json.loads(envelope["result"])
            if not isinstance(proposal, dict):
                raise ValueError("missing structured_output")
        except (ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("Claude did not produce a valid JSON proposal") from error
        return ProviderResult(proposal, self.name, model, version)


def get_provider(name: str) -> Provider:
    if name == "codex":
        return CodexProvider()
    if name == "claude":
        return ClaudeProvider()
    raise ValueError(f"unknown provider: {name}")


def _require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} CLI is not installed")
    return path


def _version(command: list[str]) -> str:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return (completed.stdout or completed.stderr).strip().splitlines()[0]


def _failure(name: str, completed: subprocess.CompletedProcess[str]) -> str:
    detail = (completed.stderr or completed.stdout).strip()[-4000:]
    return f"{name} failed with exit {completed.returncode}: {detail}"
