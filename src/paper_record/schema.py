from __future__ import annotations

from typing import Any


READ_STATUSES = {"NOT_READ", "TEXT_READ", "VISUALLY_READ"}
EVIDENCE_STATUSES = {"NOT_CHECKED", "CROSS_CHECKED", "SOURCE_CONFIRMED", "UNRESOLVED"}
TARGETS = {
    "identity",
    "summary",
    "structure",
    "claims",
    "figures",
    "tables",
    "equations",
    "conflicts",
    "unresolved",
    "notes",
}
ACTIONS = {"upsert", "replace", "append", "resolve"}

MANIFEST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "paper_id", "canonical_language", "active_revision",
        "source", "parsers", "canonical", "assets", "warnings",
    ],
    "properties": {
        "schema_version": {"const": 1},
        "paper_id": {"type": "string", "minLength": 1},
        "canonical_language": {"const": "en"},
        "active_revision": {"type": ["string", "null"], "pattern": "^r[0-9]{4}$"},
        "source": {"type": "object"},
        "parsers": {"type": "object"},
        "canonical": {"type": "object"},
        "assets": {"type": "array"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
}

RECEIPT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["path", "kind", "sha256", "revision"],
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "kind": {"enum": ["manifest", "text", "visual", "canonical"]},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "revision": {"type": ["string", "null"]},
    },
}

REVIEW_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schema_version", "read_id", "proposal_sha256", "decisions"],
    "properties": {
        "schema_version": {"const": 1},
        "read_id": {"type": "string", "pattern": "^READ-[0-9]{4}$"},
        "proposal_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["item_id", "decision"],
                "properties": {
                    "item_id": {"type": "string"},
                    "decision": {"enum": ["ACCEPTED", "REJECTED", "FEEDBACK"]},
                    "feedback": {"type": ["string", "null"]},
                },
            },
        },
    },
}

CANONICAL_STATE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version", "canonical_version", "identity", "summary", "structure",
        "claims", "figures", "tables", "equations", "conflicts", "unresolved", "ledger",
    ],
    "properties": {
        "schema_version": {"const": 1},
        "canonical_version": {"type": "integer", "minimum": 0},
        "identity": {"type": "object"},
        "summary": {"type": "object"},
        "structure": {"type": "object"},
        "claims": {"type": "array"},
        "figures": {"type": "array"},
        "tables": {"type": "array"},
        "equations": {"type": "array"},
        "conflicts": {"type": "array"},
        "unresolved": {"type": "array"},
        "ledger": {"type": "array"},
    },
}

EVENT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "event_id", "timestamp", "run_id", "paper_id", "command",
        "event_type", "status", "duration_ms", "context", "error",
    ],
    "properties": {
        "schema_version": {"const": 1},
        "event_id": {"type": "string", "pattern": "^EVT-[0-9a-f]+$"},
        "timestamp": {"type": "string"},
        "run_id": {"type": "string", "pattern": "^RUN-[0-9a-f]+$"},
        "paper_id": {"type": "string"},
        "command": {"type": "string"},
        "event_type": {"type": "string"},
        "status": {"type": "string"},
        "duration_ms": {"type": "integer", "minimum": 0},
        "context": {"type": "object"},
        "error": {"type": ["string", "null"]},
    },
}


PROPOSAL_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["reading", "operations", "evidence_requests"],
    "properties": {
        "reading": {
            "type": "object",
            "additionalProperties": True,
            "required": ["purpose", "result"],
            "properties": {
                "purpose": {"type": "string"},
                "result": {"type": "string"},
            },
        },
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "item_id",
                    "action",
                    "target",
                    "content",
                    "provenance",
                    "read_status",
                    "evidence_status",
                ],
                "properties": {
                    "item_id": {"type": "string", "minLength": 1},
                    "action": {"enum": sorted(ACTIONS)},
                    "target": {"enum": sorted(TARGETS)},
                    "content": {},
                    "provenance": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": True,
                            "required": ["source"],
                            "properties": {
                                "source": {"type": "string"},
                                "page": {"type": ["integer", "null"]},
                                "locator": {"type": ["string", "null"]},
                                "excerpt": {"type": ["string", "null"]},
                            },
                        },
                    },
                    "read_status": {"enum": sorted(READ_STATUSES)},
                    "evidence_status": {"enum": sorted(EVIDENCE_STATUSES)},
                },
            },
        },
        "evidence_requests": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["reason"],
                "properties": {
                    "reason": {"type": "string"},
                    "page": {"type": ["integer", "null"]},
                    "asset": {"type": ["string", "null"]},
                },
            },
        },
    },
}


def validate_proposal(proposal: dict[str, Any], receipts: list[dict[str, Any]]) -> None:
    if not isinstance(proposal.get("reading"), dict):
        raise ValueError("proposal.reading must be an object")
    if not isinstance(proposal.get("operations"), list):
        raise ValueError("proposal.operations must be an array")
    if not isinstance(proposal.get("evidence_requests"), list):
        raise ValueError("proposal.evidence_requests must be an array")

    receipt_paths = {item["path"] for item in receipts}
    visual_paths = {item["path"] for item in receipts if item.get("kind") == "visual"}
    seen: set[str] = set()
    for operation in proposal["operations"]:
        missing = {
            "item_id", "action", "target", "content", "provenance",
            "read_status", "evidence_status",
        } - operation.keys()
        if missing:
            raise ValueError(f"operation missing fields: {sorted(missing)}")
        item_id = operation["item_id"]
        if item_id in seen:
            raise ValueError(f"duplicate operation item_id: {item_id}")
        seen.add(item_id)
        if operation["action"] not in ACTIONS or operation["target"] not in TARGETS:
            raise ValueError(f"invalid operation action/target: {item_id}")
        if operation["read_status"] not in READ_STATUSES:
            raise ValueError(f"invalid read_status: {item_id}")
        if operation["evidence_status"] not in EVIDENCE_STATUSES:
            raise ValueError(f"invalid evidence_status: {item_id}")
        sources = {p.get("source") for p in operation["provenance"]}
        if not sources <= receipt_paths:
            raise ValueError(f"operation cites input that was not provided: {item_id}")
        if operation["evidence_status"] == "CROSS_CHECKED" and not {
            "01_native.md", "02_structured.md"
        } <= sources:
            raise ValueError(f"CROSS_CHECKED requires both textual sources: {item_id}")
        if operation["evidence_status"] == "SOURCE_CONFIRMED":
            if not (sources & visual_paths):
                raise ValueError(f"SOURCE_CONFIRMED requires provided visual evidence: {item_id}")
        if operation["read_status"] == "VISUALLY_READ" and not (sources & visual_paths):
            raise ValueError(f"VISUALLY_READ requires provided visual evidence: {item_id}")


def schema_json() -> str:
    import json

    return json.dumps(PROPOSAL_SCHEMA, ensure_ascii=False, indent=2) + "\n"


SCHEMAS = {
    "manifest": MANIFEST_SCHEMA,
    "proposal": PROPOSAL_SCHEMA,
    "receipt": RECEIPT_SCHEMA,
    "review": REVIEW_SCHEMA,
    "canonical-state": CANONICAL_STATE_SCHEMA,
    "event": EVENT_SCHEMA,
}
