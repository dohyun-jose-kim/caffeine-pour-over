from __future__ import annotations

import json
import os
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
        error = context.pop("error", None)
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
            "context": context,
            "error": error,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
