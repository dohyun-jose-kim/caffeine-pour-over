from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    detail: str
    required: bool = False


def run_checks(output_root: Path) -> list[Check]:
    python_ok = (3, 12) <= sys.version_info[:2] < (3, 14)
    output_parent = output_root.resolve().parent
    checks = [
        Check(
            "python",
            "OK" if python_ok else "FAIL",
            platform.python_version(),
            required=True,
        ),
        _command("uv", required=True),
        _module("pymupdf4llm", required=True),
        _command("mineru"),
        _command("codex"),
        _command("claude"),
        Check("platform", "OK" if sys.platform == "darwin" else "WARN", platform.platform()),
        Check(
            "output-root",
            "OK" if output_parent.exists() and output_parent.is_dir() else "WARN",
            str(output_root),
        ),
    ]
    return checks


def _command(name: str, required: bool = False) -> Check:
    path = shutil.which(name)
    return Check(name, "OK" if path else ("FAIL" if required else "WARN"), path or "not found", required)


def _module(name: str, required: bool = False) -> Check:
    found = importlib.util.find_spec(name) is not None
    return Check(
        name,
        "OK" if found else ("FAIL" if required else "WARN"),
        "importable" if found else "not importable",
        required,
    )
