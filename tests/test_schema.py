import pytest

from paper_record.schema import validate_proposal


def operation(**changes):
    value = {
        "item_id": "CLAIM-0001",
        "action": "upsert",
        "target": "claims",
        "content": {"claim": "Example"},
        "provenance": [{"source": "01_native.md", "page": 1}],
        "read_status": "TEXT_READ",
        "evidence_status": "NOT_CHECKED",
    }
    value.update(changes)
    return value


def proposal(op):
    return {
        "reading": {"purpose": "test", "result": "complete"},
        "operations": [op],
        "evidence_requests": [],
    }


def test_cross_checked_requires_both_text_sources() -> None:
    with pytest.raises(ValueError, match="both textual"):
        validate_proposal(
            proposal(operation(evidence_status="CROSS_CHECKED")),
            [{"path": "01_native.md", "kind": "text"}],
        )


def test_visual_status_requires_visual_receipt() -> None:
    with pytest.raises(ValueError, match="visual evidence"):
        validate_proposal(
            proposal(operation(read_status="VISUALLY_READ")),
            [{"path": "01_native.md", "kind": "text"}],
        )


def test_cross_checked_accepts_two_sources() -> None:
    op = operation(
        evidence_status="CROSS_CHECKED",
        provenance=[{"source": "01_native.md"}, {"source": "02_structured.md"}],
    )
    validate_proposal(
        proposal(op),
        [
            {"path": "01_native.md", "kind": "text"},
            {"path": "02_structured.md", "kind": "text"},
        ],
    )
