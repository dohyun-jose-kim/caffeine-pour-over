from pathlib import Path

from paper_record.ingest import ingest_native
from paper_record.manifest import load_manifest


class FakeExtractor:
    version = "test-1"

    def __init__(self, pages=None):
        self.pages = pages or ["First page", "", "Third page"]

    def extract(self, pdf: Path):
        assert pdf.read_bytes().startswith(b"%PDF")
        return self.pages, len(self.pages)


class FailsOnceExtractor(FakeExtractor):
    calls = 0

    def extract(self, pdf: Path):
        self.__class__.calls += 1
        if self.__class__.calls == 1:
            raise RuntimeError("synthetic extraction failure")
        return super().extract(pdf)


def fake_pdf(path: Path, content: bytes = b"%PDF-1.4\nfixture") -> Path:
    path.write_bytes(content)
    return path


def test_native_ingest_creates_atomic_active_view(tmp_path: Path) -> None:
    source = fake_pdf(tmp_path / "source.pdf")
    paper_dir, manifest, changed = ingest_native(
        source, tmp_path / "papers", extractor=FakeExtractor()
    )
    assert changed
    assert (paper_dir / ".paper-record" / "active").is_symlink()
    assert (paper_dir / "paper.pdf").read_bytes() == source.read_bytes()
    markdown = (paper_dir / "01_native.md").read_text(encoding="utf-8")
    assert markdown.count("<!-- PAGE:") == 3
    assert "<!-- EMPTY_NATIVE_TEXT -->" in markdown
    assert manifest["parsers"]["native"]["status"] == "SUCCEEDED"
    assert manifest["parsers"]["structured"]["status"] == "PENDING"
    assert manifest["revision_status"] == "INCOMPLETE"


def test_identical_native_ingest_is_noop(tmp_path: Path) -> None:
    source = fake_pdf(tmp_path / "source.pdf")
    root = tmp_path / "papers"
    _, first, changed = ingest_native(source, root, extractor=FakeExtractor())
    assert changed
    _, second, changed = ingest_native(source, root, extractor=FakeExtractor())
    assert not changed
    assert second["active_revision"] == first["active_revision"]


def test_changed_source_creates_new_revision_and_preserves_old(tmp_path: Path) -> None:
    source = fake_pdf(tmp_path / "source.pdf")
    root = tmp_path / "papers"
    paper_dir, _, _ = ingest_native(source, root, extractor=FakeExtractor(["old"]))
    source.write_bytes(b"%PDF-1.4\nchanged")
    _, manifest, _ = ingest_native(source, root, extractor=FakeExtractor(["new"]))
    assert manifest["active_revision"] == "r0002"
    revisions = paper_dir / ".paper-record" / "revisions"
    assert (revisions / "r0001" / "01_native.md").exists()
    assert "new" in (paper_dir / "01_native.md").read_text(encoding="utf-8")
    assert "old" in (revisions / "r0001" / "01_native.md").read_text(encoding="utf-8")


def test_status_manifest_follows_active_revision(tmp_path: Path) -> None:
    source = fake_pdf(tmp_path / "source.pdf")
    paper_dir, expected, _ = ingest_native(source, tmp_path / "papers", extractor=FakeExtractor())
    assert load_manifest(paper_dir)["active_revision"] == expected["active_revision"]


def test_failed_native_revision_is_resumed(tmp_path: Path) -> None:
    source = fake_pdf(tmp_path / "source.pdf")
    root = tmp_path / "papers"
    FailsOnceExtractor.calls = 0
    try:
        ingest_native(source, root, extractor=FailsOnceExtractor())
    except RuntimeError as error:
        assert "synthetic" in str(error)
    else:
        raise AssertionError("first extraction should fail")
    paper_dir, manifest, changed = ingest_native(source, root, extractor=FailsOnceExtractor())
    assert changed
    assert manifest["active_revision"] == "r0001"
    assert (paper_dir / ".paper-record" / "revisions" / "r0001").exists()
