from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .schema import CANONICAL_STATE_SCHEMA, TARGETS
from .util import atomic_write_text


STATE_START = "<!-- PAPER_RECORD_STATE_START\n"
STATE_END = "\nPAPER_RECORD_STATE_END -->"
NOTES_START = "<!-- USER_NOTES_START -->"
NOTES_END = "<!-- USER_NOTES_END -->"

SECTION_TITLES = {
    "identity": "Paper Identity",
    "summary": "Canonical Summary",
    "structure": "Canonical Structure",
    "claims": "Quantitative Claims",
    "figures": "Figures",
    "tables": "Tables",
    "equations": "Equations",
    "conflicts": "Source Disagreements",
    "unresolved": "Unresolved Items",
    "notes": "Machine Notes",
}


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "canonical_version": 0,
        "identity": {},
        "summary": {},
        "structure": {},
        "claims": [],
        "figures": [],
        "tables": [],
        "equations": [],
        "conflicts": [],
        "unresolved": [],
        "notes": [],
        "ledger": [],
    }


def ensure_canonical_scaffold(paper_dir: Path) -> bool:
    path = paper_dir / "03_canonical.md"
    if path.exists():
        return False
    atomic_write_text(path, render_canonical(empty_state(), ""))
    return True


def load_canonical(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    notes = _between(text, NOTES_START, NOTES_END).strip("\n")
    if STATE_START not in text:
        return empty_state(), notes
    raw = _between(text, STATE_START, STATE_END)
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("03_canonical.md contains malformed managed state") from error
    validate_canonical_state(state)
    return state, notes


def validate_canonical_state(state: dict[str, Any]) -> None:
    required = set(CANONICAL_STATE_SCHEMA["required"]) | {"notes"}
    if not isinstance(state, dict) or not required <= state.keys():
        raise ValueError("canonical state is missing required fields")
    if state.get("schema_version") != 1:
        raise ValueError("unsupported canonical schema version")
    if not isinstance(state.get("canonical_version"), int) or state["canonical_version"] < 0:
        raise ValueError("invalid canonical version")
    for name in ("identity", "summary", "structure"):
        if not isinstance(state[name], dict):
            raise ValueError(f"canonical {name} must be an object")
    list_sections = (
        "claims", "figures", "tables", "equations", "conflicts", "unresolved", "notes", "ledger"
    )
    for name in list_sections:
        if not isinstance(state[name], list):
            raise ValueError(f"canonical {name} must be an array")


def apply_operations(state: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    updated = deepcopy(state)
    for operation in operations:
        target = operation["target"]
        if target not in TARGETS:
            raise ValueError(f"unsupported canonical target: {target}")
        item = {
            "item_id": operation["item_id"],
            "content": deepcopy(operation["content"]),
            "provenance": deepcopy(operation["provenance"]),
            "read_status": operation["read_status"],
            "evidence_status": operation["evidence_status"],
        }
        if target in {"identity", "summary", "structure"}:
            if operation["action"] == "resolve":
                updated[target].pop(operation["item_id"], None)
            else:
                updated[target][operation["item_id"]] = item
        else:
            values = updated[target]
            index = next(
                (i for i, value in enumerate(values) if value.get("item_id") == item["item_id"]),
                None,
            )
            if operation["action"] == "resolve":
                if index is not None:
                    values.pop(index)
            elif index is None:
                values.append(item)
            else:
                values[index] = item
    return updated


def render_canonical(state: dict[str, Any], user_notes: str) -> str:
    validate_canonical_state(state)
    reading_status = "TEXT_READ" if state["ledger"] else "NOT_READ"
    lines = [
        "---",
        "schema_version: 1",
        "record_type: canonical",
        f"canonical_version: {state['canonical_version']}",
        "canonical_language: en",
        f"reading_status: {reading_status}",
        "---",
        "",
        "> This file is a cumulative LLM reading record. The original PDF remains authoritative.",
        "> Conflicting parser content must remain unresolved or be resolved from original visual evidence.",
        "",
        STATE_START.rstrip("\n"),
        json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        STATE_END.lstrip("\n"),
        "",
        "# Current Canonical Record",
        "",
    ]
    for key, title in SECTION_TITLES.items():
        lines.extend([f"## {title}", ""])
        values = state[key]
        entries = list(values.values()) if isinstance(values, dict) else values
        if not entries:
            lines.extend(["None recorded.", ""])
        else:
            for item in entries:
                lines.extend(_render_item(item))
    lines.extend(["## Canonical Notes", "", NOTES_START])
    if user_notes:
        lines.extend(user_notes.splitlines())
    lines.extend([NOTES_END, "", "# Reading Ledger", ""])
    if not state["ledger"]:
        lines.extend(["No reads recorded.", ""])
    else:
        for entry in state["ledger"]:
            lines.extend(
                [
                    f"## {entry['read_id']}",
                    "",
                    f"- Applied: {entry['applied_at']}",
                    f"- Provider: {entry['provider']}",
                    f"- Purpose: {entry['purpose']}",
                    f"- Result: {entry['result']}",
                    f"- Accepted: {entry['accepted_count']}",
                    f"- Rejected: {entry['rejected_count']}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _render_item(item: dict[str, Any]) -> list[str]:
    content = item["content"]
    title = content.get("title") or item["item_id"]
    lines = [f"### {title}", "", content.get("body", "")]
    if content.get("value") is not None:
        value = content["value"]
        unit = f" {content['unit']}" if content.get("unit") else ""
        lines.extend(["", f"Value: {value}{unit}"])
    lines.extend(
        [
            "",
            f"- Item ID: `{item['item_id']}`",
            f"- Read status: `{item['read_status']}`",
            f"- Evidence status: `{item['evidence_status']}`",
        ]
    )
    for source in item["provenance"]:
        location = f", page {source['page']}" if source.get("page") else ""
        locator = f", {source['locator']}" if source.get("locator") else ""
        lines.append(f"- Source: `{source['source']}`{location}{locator}")
    lines.append("")
    return lines


def _between(text: str, start: str, end: str) -> str:
    pattern = re.escape(start) + r"(.*?)" + re.escape(end)
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1) if match else ""
