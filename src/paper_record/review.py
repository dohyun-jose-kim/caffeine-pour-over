from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .canonical import apply_operations, load_canonical, render_canonical
from .manifest import load_manifest
from .providers import Provider, get_provider
from .reading import _validate_excerpts
from .schema import PROPOSAL_SCHEMA, validate_proposal
from .util import atomic_write_json, atomic_write_text, sha256_file, utc_now


Decision = dict[str, str | None]


def load_proposal(paper_dir: Path, read_id: str) -> tuple[Path, dict[str, Any]]:
    path = paper_dir / ".paper-record" / "reviews" / read_id / "proposal.json"
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"proposal does not exist: {read_id}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"proposal is malformed: {read_id}") from error
    for field in ("read_id", "base_revision", "base_canonical_version", "receipts", "proposal"):
        if field not in envelope:
            raise ValueError(f"proposal envelope is missing {field}")
    if envelope["read_id"] != read_id:
        raise ValueError("proposal read ID does not match its directory")
    validate_proposal(envelope["proposal"], envelope["receipts"])
    return path, envelope


def assert_fresh(paper_dir: Path, envelope: dict[str, Any]) -> tuple[dict[str, Any], str]:
    manifest = load_manifest(paper_dir)
    if manifest is None or manifest.get("revision_status") != "COMPLETE":
        raise RuntimeError("active paper revision is missing or incomplete")
    state, notes = load_canonical(paper_dir / "03_canonical.md")
    if envelope["base_revision"] != manifest["active_revision"]:
        raise RuntimeError("stale proposal: active input revision changed")
    if envelope["base_canonical_version"] != state["canonical_version"]:
        raise RuntimeError("stale proposal: canonical version changed")
    for receipt in envelope["receipts"]:
        source = paper_dir / receipt["path"]
        if not source.is_file() or sha256_file(source) != receipt["sha256"]:
            raise RuntimeError(f"stale proposal: input changed: {receipt['path']}")
    return state, notes


def approve_all(envelope: dict[str, Any]) -> list[Decision]:
    return [
        {"item_id": item["item_id"], "decision": "ACCEPTED", "feedback": None}
        for item in envelope["proposal"]["operations"]
    ]


def apply_review(
    paper_dir: Path,
    read_id: str,
    decisions: list[Decision],
    *,
    before_commit: Callable[[], None] | None = None,
) -> Path:
    paper_dir = paper_dir.expanduser().resolve()
    log = AuditLog(paper_dir, "review")
    log.event("COMMAND_STARTED", "RUNNING", read_id=read_id)
    try:
        result = _apply_review(paper_dir, read_id, decisions, before_commit=before_commit)
    except BaseException as error:
        log.event("COMMAND_COMPLETED", "FAILED", read_id=read_id, error=str(error))
        raise
    log.event(
        "COMMAND_COMPLETED",
        "SUCCEEDED",
        read_id=read_id,
        artifact=str(result.relative_to(paper_dir)),
    )
    return result


def _apply_review(
    paper_dir: Path,
    read_id: str,
    decisions: list[Decision],
    *,
    before_commit: Callable[[], None] | None = None,
) -> Path:
    paper_dir = paper_dir.expanduser().resolve()
    proposal_path, envelope = load_proposal(paper_dir, read_id)
    proposal_sha256 = sha256_file(proposal_path)
    state, notes = assert_fresh(paper_dir, envelope)
    _validate_excerpts(envelope["proposal"], paper_dir)
    operations = envelope["proposal"]["operations"]
    by_id = {item["item_id"]: item for item in operations}
    decision_by_id: dict[str, Decision] = {}
    for decision in decisions:
        item_id = str(decision.get("item_id", ""))
        if item_id in decision_by_id:
            raise ValueError(f"duplicate review decision: {item_id}")
        if item_id not in by_id:
            raise ValueError(f"review decision targets unknown item: {item_id}")
        if decision.get("decision") not in {"ACCEPTED", "REJECTED"}:
            raise ValueError(f"review is incomplete for item: {item_id}")
        decision_by_id[item_id] = decision
    missing = set(by_id) - set(decision_by_id)
    if missing:
        raise ValueError(f"review is missing decisions for: {', '.join(sorted(missing))}")

    accepted = [
        item for item in operations if decision_by_id[item["item_id"]]["decision"] == "ACCEPTED"
    ]
    rejected = [
        item for item in operations if decision_by_id[item["item_id"]]["decision"] == "REJECTED"
    ]
    updated = apply_operations(state, accepted)
    updated["canonical_version"] += 1
    updated["ledger"].append(
        {
            "read_id": read_id,
            "applied_at": utc_now(),
            "provider": envelope["provider"],
            "purpose": envelope["proposal"]["reading"]["purpose"],
            "result": envelope["proposal"]["reading"]["result"],
            "base_revision": envelope["base_revision"],
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
        }
    )
    canonical_text = render_canonical(updated, notes)
    review = {
        "schema_version": 1,
        "read_id": read_id,
        "proposal_sha256": proposal_sha256,
        "reviewed_at": utc_now(),
        "canonical_version": updated["canonical_version"],
        "decisions": decisions,
    }
    log = AuditLog(paper_dir, "review")
    log.event("REVIEW_STARTED", "RUNNING", read_id=read_id, item_count=len(operations))
    for decision in decisions:
        log.event(
            "REVIEW_DECISION",
            "SUCCEEDED",
            read_id=read_id,
            item_id=decision["item_id"],
            decision=decision["decision"],
            has_feedback=bool(decision.get("feedback")),
        )
    try:
        if before_commit:
            before_commit()
        if sha256_file(proposal_path) != proposal_sha256:
            raise RuntimeError("proposal changed during review")
        atomic_write_text(paper_dir / "03_canonical.md", canonical_text)
        atomic_write_json(proposal_path.parent / "review.json", review)
        _update_manifest_version(paper_dir, updated["canonical_version"], envelope["base_revision"])
        log.event(
            "CANONICAL_APPLIED",
            "SUCCEEDED",
            read_id=read_id,
            canonical_version=updated["canonical_version"],
            accepted_count=len(accepted),
            rejected_count=len(rejected),
            artifact="03_canonical.md",
            artifact_sha256=sha256_file(paper_dir / "03_canonical.md"),
        )
    except BaseException as error:
        log.event("CANONICAL_APPLIED", "FAILED", read_id=read_id, error=str(error))
        raise
    return proposal_path.parent / "review.json"


def regenerate_item(
    paper_dir: Path,
    read_id: str,
    item_id: str,
    feedback: str,
    *,
    provider_name: str = "codex",
    model: str | None = None,
    provider: Provider | None = None,
) -> dict[str, Any]:
    paper_dir = paper_dir.expanduser().resolve()
    proposal_path, envelope = load_proposal(paper_dir, read_id)
    assert_fresh(paper_dir, envelope)
    _validate_excerpts(envelope["proposal"], paper_dir)
    matches = [item for item in envelope["proposal"]["operations"] if item["item_id"] == item_id]
    if not matches:
        raise ValueError(f"proposal item does not exist: {item_id}")
    inputs = []
    for receipt in envelope["receipts"]:
        if receipt["kind"] in {"manifest", "text", "canonical"}:
            path = paper_dir / receipt["path"]
            body = path.read_text(encoding="utf-8")
            inputs.append(
                f"===== BEGIN INPUT: {receipt['path']} =====\n{body}\n===== END INPUT ====="
            )
    prompt = "\n".join(
        [
            "Regenerate exactly one operation in a scientific reading proposal.",
            f"The sole operation must retain item_id {item_id}.",
            "Do not return or alter any other operation. Return an empty evidence_requests array.",
            "Every non-null excerpt must be an exact substring of its named input.",
            f"Reviewer feedback: {feedback}",
            f"Previous operation: {json.dumps(matches[0], ensure_ascii=False)}",
            *inputs,
        ]
    )
    implementation = provider or get_provider(provider_name)
    result = implementation.run(
        prompt=prompt, schema=PROPOSAL_SCHEMA, paper_dir=paper_dir, images=[], model=model
    )
    validate_proposal(result.proposal, envelope["receipts"])
    operations = result.proposal["operations"]
    if len(operations) != 1 or operations[0]["item_id"] != item_id:
        raise ValueError("feedback regeneration changed operations outside its target")
    _validate_excerpts(result.proposal, paper_dir)
    revised = deepcopy(envelope)
    index = next(
        i
        for i, item in enumerate(revised["proposal"]["operations"])
        if item["item_id"] == item_id
    )
    revised["proposal"]["operations"][index] = operations[0]
    generation_dir = proposal_path.parent / "feedback"
    generation_dir.mkdir(exist_ok=True)
    number = len(list(generation_dir.glob("*.json"))) + 1
    artifact = generation_dir / f"{number:04d}-{item_id}.json"
    atomic_write_json(
        artifact,
        {"feedback": feedback, "provider": result.provider, "response": result.proposal},
    )
    atomic_write_json(proposal_path, revised)
    AuditLog(paper_dir, "review").event(
        "REVIEW_FEEDBACK",
        "SUCCEEDED",
        read_id=read_id,
        item_id=item_id,
        artifact=str(artifact.relative_to(paper_dir)),
        artifact_sha256=sha256_file(artifact),
    )
    return operations[0]


def _update_manifest_version(paper_dir: Path, version: int, revision: str) -> None:
    manifest = load_manifest(paper_dir)
    if manifest is None:
        raise RuntimeError("manifest disappeared during canonical apply")
    manifest["canonical"]["version"] = version
    revisions = list(manifest["canonical"].get("based_on_revisions", []))
    if revision not in revisions:
        revisions.append(revision)
    manifest["canonical"]["based_on_revisions"] = revisions
    manifest["canonical"]["review_required"] = False
    active_manifest = (
        paper_dir
        / ".paper-record"
        / "revisions"
        / manifest["active_revision"]
        / "manifest.yaml"
    )
    atomic_write_json(active_manifest, manifest)
