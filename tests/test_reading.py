from pathlib import Path

from paper_record.providers import ProviderResult
from paper_record.reading import read_paper
from paper_record.util import atomic_write_json


class FakeProvider:
    name = "codex"

    def __init__(self, proposal):
        self.proposal = proposal
        self.received_prompt = ""

    def run(self, *, prompt, schema, paper_dir, images, model):
        self.received_prompt = prompt
        return ProviderResult(self.proposal, self.name, model, "fake 1.0")


def valid_proposal():
    return {
        "reading": {"purpose": "Initial", "result": "Reviewed both text records"},
        "operations": [
            {
                "item_id": "CLAIM-0001",
                "action": "upsert",
                "target": "claims",
                "content": {"title": "Finding", "body": "Alpha", "value": None, "unit": None},
                "provenance": [
                    {"source": "01_native.md", "page": 1, "locator": None, "excerpt": "Alpha"},
                    {"source": "02_structured.md", "page": 1, "locator": None, "excerpt": "Alpha"},
                ],
                "read_status": "TEXT_READ",
                "evidence_status": "CROSS_CHECKED",
            }
        ],
        "evidence_requests": [
            {"reason": "Inspect the main figure", "page": 1, "asset": "assets/figures/fig_001.png"}
        ],
    }


def paper_record(tmp_path: Path) -> Path:
    paper = tmp_path / "paper"
    paper.mkdir()
    (paper / "01_native.md").write_text("Alpha native", encoding="utf-8")
    (paper / "02_structured.md").write_text("Alpha structured", encoding="utf-8")
    (paper / "03_canonical.md").write_text("# Reading Ledger\n", encoding="utf-8")
    atomic_write_json(
        paper / "manifest.yaml",
        {
            "active_revision": "r0001",
            "revision_status": "COMPLETE",
            "canonical": {"version": 0},
        },
    )
    return paper


def test_read_creates_validated_noncanonical_proposal(tmp_path: Path) -> None:
    paper = paper_record(tmp_path)
    provider = FakeProvider(valid_proposal())
    read_id, path = read_paper(paper, provider=provider)
    assert read_id == "READ-0001"
    assert path.exists()
    assert "BEGIN INPUT: 01_native.md" in provider.received_prompt
    assert (paper / "03_canonical.md").read_text(encoding="utf-8") == "# Reading Ledger\n"


def test_read_rejects_untraceable_excerpt(tmp_path: Path) -> None:
    paper = paper_record(tmp_path)
    proposal = valid_proposal()
    proposal["operations"][0]["provenance"][0]["excerpt"] = "not present"
    try:
        read_paper(paper, provider=FakeProvider(proposal))
    except ValueError as error:
        assert "was not found" in str(error)
        raw = paper / ".paper-record" / "reviews" / "READ-0001" / "provider-response.json"
        assert raw.exists()
        assert __import__("json").loads(raw.read_text())["operations"][0]["item_id"] == "CLAIM-0001"
    else:
        raise AssertionError("untraceable excerpt should fail")


def test_read_requires_complete_revision(tmp_path: Path) -> None:
    paper = paper_record(tmp_path)
    manifest = __import__("json").loads((paper / "manifest.yaml").read_text())
    manifest["revision_status"] = "INCOMPLETE"
    atomic_write_json(paper / "manifest.yaml", manifest)
    try:
        read_paper(paper, provider=FakeProvider(valid_proposal()))
    except RuntimeError as error:
        assert "incomplete" in str(error)
    else:
        raise AssertionError("incomplete revision should fail")


def test_read_renders_explicit_pdf_pages_as_visual_receipts(tmp_path: Path) -> None:
    import pymupdf

    paper = paper_record(tmp_path)
    document = pymupdf.open()
    document.new_page()
    document.save(paper / "paper.pdf")
    document.close()
    provider = FakeProvider(valid_proposal())
    _, proposal_path = read_paper(paper, provider=provider, pages="1")
    envelope = __import__("json").loads(proposal_path.read_text())
    visuals = [item for item in envelope["receipts"] if item["kind"] == "visual"]
    assert len(visuals) == 1
    assert visuals[0]["path"].endswith("inputs/page_0001.png")
