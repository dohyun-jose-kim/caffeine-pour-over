from pathlib import Path

from paper_record.canonical import ensure_canonical_scaffold, load_canonical
from paper_record.ingest import ingest_native
from paper_record.providers import ProviderResult
from paper_record.reading import read_paper
from paper_record.review import apply_review, approve_all, load_proposal
from paper_record.structured import ingest_structured

from .fixtures import representative_scientific_pdf
from .test_native import FakeExtractor
from .test_structured import FakeMinerU


class ConflictProvider:
    name = "codex"

    def run(self, **kwargs):
        provenance = [
            {"source": "01_native.md", "page": 1, "locator": "Results", "excerpt": None},
            {"source": "02_structured.md", "page": 1, "locator": "Results", "excerpt": None},
        ]
        operations = [
            {
                "item_id": "CONFLICT-MIC-1",
                "action": "upsert",
                "target": "conflicts",
                "content": {
                    "title": "MIC mismatch",
                    "body": "Native and structured records disagree; no winner selected.",
                    "value": None,
                    "unit": None,
                },
                "provenance": provenance,
                "read_status": "TEXT_READ",
                "evidence_status": "UNRESOLVED",
            },
            {
                "item_id": "UNRESOLVED-MIC-1",
                "action": "upsert",
                "target": "unresolved",
                "content": {
                    "title": "Verify MIC",
                    "body": "Inspect the original table before choosing a value.",
                    "value": None,
                    "unit": None,
                },
                "provenance": provenance,
                "read_status": "TEXT_READ",
                "evidence_status": "UNRESOLVED",
            },
        ]
        proposal = {
            "reading": {"purpose": "Initial", "result": "Conflict preserved"},
            "operations": operations,
            "evidence_requests": [
                {"reason": "Inspect original table", "page": 1, "asset": None}
            ],
        }
        return ProviderResult(proposal, self.name, None, "mock")


def test_three_layer_workflow_end_to_end_without_network(tmp_path: Path) -> None:
    source = representative_scientific_pdf(tmp_path / "paper.pdf")
    paper, _, _ = ingest_native(
        source,
        tmp_path / "papers",
        extractor=FakeExtractor(["MIC = 2 ug/mL"]),
    )
    manifest, _ = ingest_structured(paper, FakeMinerU())
    ensure_canonical_scaffold(paper)
    read_id, _ = read_paper(paper, provider=ConflictProvider())
    _, envelope = load_proposal(paper, read_id)
    apply_review(paper, read_id, approve_all(envelope))

    state, _ = load_canonical(paper / "03_canonical.md")
    assert manifest["revision_status"] == "COMPLETE"
    assert (paper / "01_native.md").exists()
    assert (paper / "02_structured.md").exists()
    assert state["conflicts"][0]["evidence_status"] == "UNRESOLVED"
    assert state["unresolved"][0]["item_id"] == "UNRESOLVED-MIC-1"
    assert state["ledger"][0]["read_id"] == read_id
