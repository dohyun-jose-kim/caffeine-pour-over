import json
from pathlib import Path

import pymupdf

from paper_record.ingest import ingest_native
from paper_record.structured import ingest_structured

from .test_native import FakeExtractor


class FakeMinerU:
    version = "test-mineru-1"

    def run(self, pdf: Path, output: Path) -> None:
        document_dir = output / "document"
        images = document_dir / "images"
        images.mkdir(parents=True)
        image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
        image.clear_with(0x6699CC)
        image.save(images / "figure.jpg")
        (document_dir / "paper.md").write_text(
            "# Structured Paper\n\n![Figure](images/figure.jpg)\n",
            encoding="utf-8",
        )
        content = [
            {"type": "image", "img_path": "images/figure.jpg", "page_idx": 0, "bbox": [100, 100, 500, 400]},
            {"type": "table", "page_idx": 0, "bbox": [100, 500, 900, 800]},
            {"type": "equation", "page_idx": 0, "bbox": [200, 820, 800, 900]},
        ]
        (document_dir / "paper_content_list.json").write_text(json.dumps(content), encoding="utf-8")


class FailsOnceMinerU(FakeMinerU):
    calls = 0

    def run(self, pdf: Path, output: Path) -> None:
        self.__class__.calls += 1
        if self.__class__.calls == 1:
            raise RuntimeError("synthetic MinerU failure")
        super().run(pdf, output)


class MissingAssetMinerU(FakeMinerU):
    def run(self, pdf: Path, output: Path) -> None:
        document_dir = output / "document"
        document_dir.mkdir(parents=True)
        (document_dir / "paper.md").write_text("# Paper\n\n![missing](missing.png)\n")
        content = [{"type": "image", "img_path": "missing.png", "page_idx": 0}]
        (document_dir / "paper_content_list.json").write_text(json.dumps(content))


def source_pdf(path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((72, 72), "fixture")
    document.save(path)
    document.close()
    return path


def test_structured_ingest_materializes_assets_and_completes_revision(tmp_path: Path) -> None:
    source = source_pdf(tmp_path / "source.pdf")
    paper_dir, _, _ = ingest_native(
        source, tmp_path / "papers", extractor=FakeExtractor(["native"])
    )
    manifest, changed = ingest_structured(paper_dir, FakeMinerU())
    assert changed
    assert manifest["revision_status"] == "COMPLETE"
    assert manifest["parsers"]["structured"]["status"] == "SUCCEEDED"
    assert [asset["status"] for asset in manifest["assets"]] == [
        "PRESERVED", "CROPPED_FROM_SOURCE", "CROPPED_FROM_SOURCE"
    ]
    structured = (paper_dir / "02_structured.md").read_text(encoding="utf-8")
    assert "<!-- PAGE: 1 -->" in structured
    assert "assets/figures/fig_001.png" in structured
    assert "### FIG-0001" in structured
    assert (paper_dir / "assets" / "tables" / "table_001.png").exists()


def test_identical_structured_ingest_is_noop(tmp_path: Path) -> None:
    source = source_pdf(tmp_path / "source.pdf")
    paper_dir, _, _ = ingest_native(
        source, tmp_path / "papers", extractor=FakeExtractor(["native"])
    )
    ingest_structured(paper_dir, FakeMinerU())
    manifest, changed = ingest_structured(paper_dir, FakeMinerU())
    assert not changed
    assert manifest["active_revision"] == "r0001"


def test_failed_structured_stage_resumes_same_incomplete_revision(tmp_path: Path) -> None:
    source = source_pdf(tmp_path / "source.pdf")
    paper_dir, _, _ = ingest_native(
        source, tmp_path / "papers", extractor=FakeExtractor(["native"])
    )
    FailsOnceMinerU.calls = 0
    try:
        ingest_structured(paper_dir, FailsOnceMinerU())
    except RuntimeError as error:
        assert "synthetic" in str(error)
    else:
        raise AssertionError("first structured extraction should fail")
    manifest, changed = ingest_structured(paper_dir, FailsOnceMinerU())
    assert changed
    assert manifest["active_revision"] == "r0001"
    assert manifest["revision_status"] == "COMPLETE"


def test_missing_visual_metadata_remains_explicit(tmp_path: Path) -> None:
    source = source_pdf(tmp_path / "source.pdf")
    paper_dir, _, _ = ingest_native(
        source, tmp_path / "papers", extractor=FakeExtractor(["native"])
    )
    manifest, _ = ingest_structured(paper_dir, MissingAssetMinerU())
    assert manifest["assets"][0]["status"] == "MISSING"
    assert manifest["assets"][0]["path"] is None
    assert "Status: MISSING" in (paper_dir / "02_structured.md").read_text()
