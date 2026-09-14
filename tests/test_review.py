import json
from pathlib import Path

import pytest

from paper_record.canonical import ensure_canonical_scaffold, load_canonical
from paper_record.providers import ProviderResult
from paper_record.review import apply_review, approve_all, load_proposal, regenerate_item
from paper_record.util import atomic_write_json, sha256_file


def operation(item_id="CLAIM-1", target="claims", body="Alpha", read_status="TEXT_READ", evidence_status="CROSS_CHECKED"):
    return {
        "item_id": item_id,
        "action": "upsert",
        "target": target,
        "content": {"title": "Finding", "body": body, "value": None, "unit": None},
        "provenance": [
            {"source": "01_native.md", "page": 1, "locator": None, "excerpt": "Alpha"},
            {"source": "02_structured.md", "page": 1, "locator": None, "excerpt": "Alpha"},
        ],
        "read_status": read_status,
        "evidence_status": evidence_status,
    }


def make_paper(tmp_path: Path, operations=None) -> Path:
    paper = tmp_path / "paper"
    revision = paper / ".paper-record" / "revisions" / "r0001"
    review = paper / ".paper-record" / "reviews" / "READ-0001"
    revision.mkdir(parents=True)
    review.mkdir(parents=True)
    (paper / "01_native.md").write_text("Alpha native", encoding="utf-8")
    (paper / "02_structured.md").write_text("Alpha structured", encoding="utf-8")
    ensure_canonical_scaffold(paper)
    canonical = paper / "03_canonical.md"
    canonical.write_text(
        canonical.read_text().replace("<!-- USER_NOTES_START -->", "<!-- USER_NOTES_START -->\nkeep me"),
        encoding="utf-8",
    )
    manifest = {
        "active_revision": "r0001",
        "revision_status": "COMPLETE",
        "canonical": {"version": 0, "based_on_revisions": [], "review_required": True},
    }
    atomic_write_json(revision / "manifest.yaml", manifest)
    (paper / "manifest.yaml").symlink_to(".paper-record/revisions/r0001/manifest.yaml")
    receipts = [
        {"path": name, "kind": kind, "sha256": sha256_file(paper / name), "revision": "r0001"}
        for name, kind in (
            ("manifest.yaml", "manifest"),
            ("01_native.md", "text"),
            ("02_structured.md", "text"),
            ("03_canonical.md", "canonical"),
        )
    ]
    envelope = {
        "schema_version": 1,
        "read_id": "READ-0001",
        "created_at": "2026-01-01T00:00:00Z",
        "provider": "codex",
        "requested_model": None,
        "provider_cli_version": "test",
        "base_revision": "r0001",
        "base_canonical_version": 0,
        "receipts": receipts,
        "proposal": {
            "reading": {"purpose": "Initial", "result": "Read both representations"},
            "operations": operations if operations is not None else [operation()],
            "evidence_requests": [],
        },
    }
    atomic_write_json(review / "proposal.json", envelope)
    return paper


def reject_all(envelope):
    return [
        {"item_id": item["item_id"], "decision": "REJECTED", "feedback": None}
        for item in envelope["proposal"]["operations"]
    ]


def test_whole_approval_applies_atomically_and_preserves_notes(tmp_path: Path) -> None:
    paper = make_paper(tmp_path)
    _, envelope = load_proposal(paper, "READ-0001")
    review = apply_review(paper, "READ-0001", approve_all(envelope))
    state, notes = load_canonical(paper / "03_canonical.md")
    assert state["canonical_version"] == 1
    assert state["claims"][0]["content"]["body"] == "Alpha"
    assert state["claims"][0]["evidence_status"] == "CROSS_CHECKED"
    assert notes == "keep me"
    assert json.loads(review.read_text())["decisions"][0]["decision"] == "ACCEPTED"


def test_all_rejected_writes_only_ledger_knowledge(tmp_path: Path) -> None:
    paper = make_paper(tmp_path)
    _, envelope = load_proposal(paper, "READ-0001")
    apply_review(paper, "READ-0001", reject_all(envelope))
    state, _ = load_canonical(paper / "03_canonical.md")
    assert state["claims"] == []
    assert state["ledger"][0]["rejected_count"] == 1


def test_stale_proposal_cannot_apply(tmp_path: Path) -> None:
    paper = make_paper(tmp_path)
    _, envelope = load_proposal(paper, "READ-0001")
    (paper / "01_native.md").write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="input changed"):
        apply_review(paper, "READ-0001", approve_all(envelope))


def test_malformed_proposal_cannot_apply(tmp_path: Path) -> None:
    paper = make_paper(tmp_path)
    path = paper / ".paper-record/reviews/READ-0001/proposal.json"
    envelope = json.loads(path.read_text())
    del envelope["proposal"]["operations"][0]["content"]["body"]
    atomic_write_json(path, envelope)
    before = (paper / "03_canonical.md").read_bytes()
    with pytest.raises(ValueError, match="malformed operation content"):
        apply_review(paper, "READ-0001", [])
    assert (paper / "03_canonical.md").read_bytes() == before


def test_interruption_before_commit_preserves_canonical_and_valid_logs(tmp_path: Path) -> None:
    paper = make_paper(tmp_path)
    _, envelope = load_proposal(paper, "READ-0001")
    before = (paper / "03_canonical.md").read_bytes()

    def interrupt():
        raise KeyboardInterrupt("simulated")

    with pytest.raises(KeyboardInterrupt):
        apply_review(paper, "READ-0001", approve_all(envelope), before_commit=interrupt)
    assert (paper / "03_canonical.md").read_bytes() == before
    lines = (paper / ".paper-record/logs/events.jsonl").read_text().splitlines()
    assert all(json.loads(line) for line in lines)
    assert json.loads(lines[-1])["status"] == "FAILED"


def test_caption_text_does_not_become_visual_read(tmp_path: Path) -> None:
    paper = make_paper(
        tmp_path,
        [operation("FIGURE-1", "figures", read_status="TEXT_READ", evidence_status="CROSS_CHECKED")],
    )
    _, envelope = load_proposal(paper, "READ-0001")
    apply_review(paper, "READ-0001", approve_all(envelope))
    state, _ = load_canonical(paper / "03_canonical.md")
    assert state["figures"][0]["read_status"] == "TEXT_READ"
    assert state["figures"][0]["evidence_status"] == "CROSS_CHECKED"


class FeedbackProvider:
    name = "codex"

    def run(self, **kwargs):
        revised = operation("CLAIM-1", body="Alpha revised")
        proposal = {
            "reading": {"purpose": "Feedback", "result": "One item revised"},
            "operations": [revised],
            "evidence_requests": [],
        }
        return ProviderResult(proposal, "codex", None, "fake")


def test_feedback_regenerates_only_target_item(tmp_path: Path) -> None:
    paper = make_paper(tmp_path, [operation("CLAIM-1"), operation("CLAIM-2")])
    revised = regenerate_item(
        paper, "READ-0001", "CLAIM-1", "clarify", provider=FeedbackProvider()
    )
    _, envelope = load_proposal(paper, "READ-0001")
    assert revised["content"]["body"] == "Alpha revised"
    assert envelope["proposal"]["operations"][1]["item_id"] == "CLAIM-2"
    assert envelope["proposal"]["operations"][1]["content"]["body"] == "Alpha"
