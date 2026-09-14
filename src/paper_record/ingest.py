from __future__ import annotations

from pathlib import Path
from typing import Any

from .audit import AuditLog
from .manifest import (
    activate_revision,
    load_manifest,
    new_manifest,
    next_revision,
    resumable_revision,
    write_manifest,
)
from .native import NATIVE_OPTIONS, NativeExtractor, PyMuPDF4LLMExtractor, render_native
from .util import atomic_copy, atomic_write_text, sha256_file, sha256_text, slugify, utc_now


def ingest_native(
    pdf: Path,
    root: Path,
    paper_id: str | None = None,
    extractor: NativeExtractor | None = None,
) -> tuple[Path, dict[str, Any], bool]:
    source = pdf.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError(f"not a readable PDF file: {pdf}")

    identity = slugify(paper_id or source.stem)
    paper_dir = root.expanduser().resolve() / identity
    paper_dir.mkdir(parents=True, exist_ok=True)
    log = AuditLog(paper_dir, "ingest")
    log.event("COMMAND_STARTED", "RUNNING", source_name=source.name)

    implementation = extractor or PyMuPDF4LLMExtractor()
    source_hash = sha256_file(source)
    current = load_manifest(paper_dir)
    if current and _native_is_identical(current, source_hash, implementation.version):
        log.event(
            "COMMAND_COMPLETED",
            "NO_OP",
            revision=current["active_revision"],
            reason="identical source and native parser settings",
        )
        return paper_dir, current, False

    resumed = resumable_revision(paper_dir, source_hash, implementation.version, NATIVE_OPTIONS)
    if resumed:
        revision_dir, manifest = resumed
        revision = manifest["active_revision"]
    else:
        revision = next_revision(paper_dir)
        revision_dir = paper_dir / ".paper-record" / "revisions" / revision
        revision_dir.mkdir(parents=True)
        manifest = new_manifest(
            identity,
            revision,
            {
                "filename": source.name,
                "sha256": source_hash,
                "size_bytes": source.stat().st_size,
                "page_count": None,
            },
        )
    manifest["parsers"]["native"] = {
        "name": "pymupdf4llm",
        "version": implementation.version,
        "options": NATIVE_OPTIONS,
        "status": "RUNNING",
        "started_at": utc_now(),
    }
    write_manifest(revision_dir, manifest)
    log.event(
        "REVISION_CREATED" if not resumed else "REVISION_RESUMED",
        "RUNNING",
        revision=revision,
    )
    log.event("STAGE_STARTED", "RUNNING", revision=revision, stage="native")

    try:
        atomic_copy(source, revision_dir / "paper.pdf")
        pages, page_count = implementation.extract(revision_dir / "paper.pdf")
        markdown, warnings = render_native(
            pages,
            revision=revision,
            source_sha256=source_hash,
            parser_version=implementation.version,
        )
        atomic_write_text(revision_dir / "01_native.md", markdown)
        manifest["source"]["page_count"] = page_count
        manifest["warnings"].extend(warnings)
        manifest["parsers"]["native"].update(
            {
                "status": "SUCCEEDED",
                "completed_at": utc_now(),
                "output_sha256": sha256_text(markdown),
            }
        )
        write_manifest(revision_dir, manifest)
        activate_revision(paper_dir, revision)
        log.event(
            "STAGE_SUCCEEDED",
            "SUCCEEDED",
            revision=revision,
            stage="native",
            page_count=page_count,
            warning_count=len(warnings),
        )
        log.event("COMMAND_COMPLETED", "INCOMPLETE", revision=revision, pending="structured")
        return paper_dir, manifest, True
    except BaseException as error:
        manifest["parsers"]["native"].update(
            {"status": "FAILED", "completed_at": utc_now(), "error": str(error)}
        )
        write_manifest(revision_dir, manifest)
        log.event("STAGE_FAILED", "FAILED", revision=revision, stage="native", error=str(error))
        log.event("COMMAND_FAILED", "FAILED", revision=revision, error=str(error))
        raise


def _native_is_identical(manifest: dict[str, Any], source_hash: str, version: str) -> bool:
    native = manifest.get("parsers", {}).get("native", {})
    return (
        manifest.get("source", {}).get("sha256") == source_hash
        and native.get("version") == version
        and native.get("options") == NATIVE_OPTIONS
        and native.get("status") == "SUCCEEDED"
    )
