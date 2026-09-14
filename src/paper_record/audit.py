from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .util import utc_now


class AuditLog:
    def __init__(self, paper_dir: Path, command: str):
        self.path = paper_dir / ".paper-record" / "logs" / "events.jsonl"
        self.command = command
        self.run_id = f"RUN-{uuid.uuid4().hex[:12]}"
        self.paper_id = paper_dir.name
        self.started = time.monotonic()

    def event(self, event_type: str, status: str, **context: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        error = _sanitize_text(str(context.pop("error", ""))) or None
        record = {
            "schema_version": 1,
            "event_id": f"EVT-{uuid.uuid4().hex}",
            "timestamp": utc_now(),
            "run_id": self.run_id,
            "paper_id": self.paper_id,
            "command": self.command,
            "event_type": event_type,
            "status": status,
            "duration_ms": round((time.monotonic() - self.started) * 1000),
            "context": _sanitize_context(context),
            "error": error,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)


_SENSITIVE_KEYS = ("prompt", "body", "content", "secret", "token", "credential", "api_key", "environment")


def _sanitize_context(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in _SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {name: _sanitize_context(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_context(item, key) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def _sanitize_text(value: str) -> str:
    value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]", value)
    value = re.sub(r"\b(?:sk|key)-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)
    return value[:2000]
