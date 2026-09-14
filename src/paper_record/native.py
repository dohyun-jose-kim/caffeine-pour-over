from __future__ import annotations

import importlib.metadata
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol


NATIVE_OPTIONS = {
    "adapter_revision": 1,
    "page_chunks": True,
    "use_layout": False,
    "use_ocr": False,
    "write_images": False,
    "ignore_images": True,
    "isolated_workdir": True,
}


class NativeExtractor(Protocol):
    version: str

    def extract(self, pdf: Path) -> tuple[list[str], int]: ...


class PyMuPDF4LLMExtractor:
    @property
    def version(self) -> str:
        return importlib.metadata.version("pymupdf4llm")

    def extract(self, pdf: Path) -> tuple[list[str], int]:
        import pymupdf

        with pymupdf.open(pdf) as document:
            page_count = document.page_count
        original_cwd = Path.cwd()
        try:
            with tempfile.TemporaryDirectory(prefix="paper-record-native-") as workdir:
                os.chdir(workdir)
                import pymupdf4llm

                pymupdf4llm.use_layout(False)
                chunks: list[dict[str, Any]] = pymupdf4llm.to_markdown(
                    str(pdf),
                    page_chunks=True,
                    write_images=False,
                    ignore_images=True,
                    show_progress=False,
                )
        finally:
            os.chdir(original_cwd)
        if len(chunks) != page_count:
            raise RuntimeError(
                f"native extractor returned {len(chunks)} chunks for {page_count} pages"
            )
        return [str(chunk.get("text", "")) for chunk in chunks], page_count


def render_native(
    pages: list[str], *, revision: str, source_sha256: str, parser_version: str
) -> tuple[str, list[str]]:
    frontmatter = [
        "---",
        "schema_version: 1",
        "record_type: native",
        f"source_revision: {revision}",
        f"source_sha256: {source_sha256}",
        "parser: pymupdf4llm",
        f"parser_version: {parser_version}",
        "ocr: false",
        "---",
        "",
    ]
    warnings: list[str] = []
    body: list[str] = []
    for number, page in enumerate(pages, start=1):
        body.extend((f"<!-- PAGE: {number} -->", ""))
        normalized = page.rstrip()
        if normalized:
            body.extend((normalized, ""))
        else:
            warnings.append(f"page {number} has no native text")
            body.extend(("<!-- EMPTY_NATIVE_TEXT -->", ""))
    return "\n".join(frontmatter + body).rstrip() + "\n", warnings
