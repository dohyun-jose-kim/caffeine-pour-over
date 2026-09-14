from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .audit import AuditLog
from .canonical import load_canonical
from .manifest import load_manifest
from .providers import Provider, get_provider
from .schema import PROPOSAL_SCHEMA, validate_proposal
from .util import atomic_write_json, ensure_within, next_numbered_id, sha256_file, utc_now


MAX_INPUT_CHARS = 1_000_000


def read_paper(
    paper_dir: Path,
    *,
    provider_name: str = "codex",
    model: str | None = None,
    purpose: str = "Initial full-paper reading",
    pages: str | None = None,
    assets: list[str] | None = None,
    provider: Provider | None = None,
) -> tuple[str, Path]:
    paper_dir = paper_dir.expanduser().resolve()
    manifest = load_manifest(paper_dir)
    if manifest is None:
        raise RuntimeError("paper manifest is missing")
    if manifest.get("revision_status") != "COMPLETE":
        raise RuntimeError("paper revision is incomplete")
    canonical = paper_dir / "03_canonical.md"
    if not canonical.exists():
        raise RuntimeError("03_canonical.md is missing; initialize the canonical scaffold first")
    canonical_state, _ = load_canonical(canonical)

    review_root = paper_dir / ".paper-record" / "reviews"
    existing = [entry.name for entry in review_root.iterdir()] if review_root.exists() else []
    read_id = next_numbered_id(existing, "READ")
    review_dir = review_root / read_id
    review_dir.mkdir(parents=True)
    log = AuditLog(paper_dir, "read")

    text_paths = [paper_dir / "manifest.yaml", paper_dir / "01_native.md", paper_dir / "02_structured.md", canonical]
    visual_paths = [_resolve_asset(paper_dir, item) for item in (assets or [])]
    if pages:
        visual_paths.extend(_render_pages(paper_dir / "paper.pdf", pages, review_dir / "inputs"))
    receipts = [_receipt(paper_dir, path, _kind(path), manifest["active_revision"]) for path in text_paths]
    receipts.extend(_receipt(paper_dir, path, "visual", manifest["active_revision"]) for path in visual_paths)
    prompt = build_prompt(text_paths, purpose)
    if visual_paths:
        prompt += "\n\nVisual evidence supplied to this read:\n" + "\n".join(
            f"- {path.relative_to(paper_dir).as_posix()}" for path in visual_paths
        )
    if len(prompt) > MAX_INPUT_CHARS:
        raise RuntimeError(
            f"combined textual input is {len(prompt)} characters; safe limit is {MAX_INPUT_CHARS}; "
            "page-aligned batching is required"
        )

    implementation = provider or get_provider(provider_name)
    log.event(
        "LLM_STARTED",
        "RUNNING",
        read_id=read_id,
        provider=implementation.name,
        input_count=len(receipts),
    )
    try:
        result = implementation.run(
            prompt=prompt,
            schema=PROPOSAL_SCHEMA,
            paper_dir=paper_dir,
            images=visual_paths,
            model=model,
        )
        # Preserve the provider response before applying local trust checks. A
        # rejected proposal is still useful diagnostic evidence and must not be
        # silently discarded.
        atomic_write_json(review_dir / "provider-response.json", result.proposal)
        validate_proposal(result.proposal, receipts)
        _validate_excerpts(result.proposal, paper_dir)
        envelope = {
            "schema_version": 1,
            "read_id": read_id,
            "created_at": utc_now(),
            "provider": result.provider,
            "requested_model": result.requested_model,
            "provider_cli_version": result.cli_version,
            "base_revision": manifest["active_revision"],
            "base_canonical_version": canonical_state["canonical_version"],
            "receipts": receipts,
            "proposal": result.proposal,
        }
        atomic_write_json(review_dir / "proposal.json", envelope)
        log.event(
            "PROPOSAL_CREATED",
            "SUCCEEDED",
            read_id=read_id,
            provider=result.provider,
            operation_count=len(result.proposal["operations"]),
            artifact=str((review_dir / "proposal.json").relative_to(paper_dir)),
        )
        log.event("LLM_COMPLETED", "SUCCEEDED", read_id=read_id, provider=result.provider)
        return read_id, review_dir / "proposal.json"
    except BaseException as error:
        log.event("LLM_COMPLETED", "FAILED", read_id=read_id, error=str(error))
        raise


def build_prompt(paths: list[Path], purpose: str) -> str:
    parts = [
        "You are creating a proposed update to a cumulative scientific paper reading record.",
        "Return only data matching the supplied JSON Schema.",
        "Do not silently reconcile conflicts between native and structured text.",
        "If they disagree, use UNRESOLVED unless original visual evidence was supplied.",
        "CROSS_CHECKED means both text records support the item; it does not mean scientifically true.",
        "Every non-null provenance excerpt must be a short, exact, verbatim substring of its named input.",
        "Do not normalize, re-typeset, or reconstruct equations inside provenance excerpts; use null when an exact quote is unavailable.",
        "Write canonical content in English while preserving source titles, units, symbols, and terms.",
        f"Reading purpose: {purpose}",
    ]
    for path in paths:
        parts.extend(
            [
                "",
                f"===== BEGIN INPUT: {path.name} =====",
                path.read_text(encoding="utf-8"),
                f"===== END INPUT: {path.name} =====",
            ]
        )
    return "\n".join(parts)


def _receipt(paper_dir: Path, path: Path, kind: str, revision: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(paper_dir).as_posix(),
        "kind": kind,
        "sha256": sha256_file(path),
        "revision": revision,
    }


def _kind(path: Path) -> str:
    if path.name == "manifest.yaml":
        return "manifest"
    if path.name == "03_canonical.md":
        return "canonical"
    return "text"


def _resolve_asset(paper_dir: Path, value: str) -> Path:
    candidate = paper_dir / value
    ensure_within(paper_dir, candidate)
    if not candidate.is_file():
        raise ValueError(f"visual asset does not exist: {value}")
    return candidate


def _render_pages(pdf: Path, specification: str, output: Path) -> list[Path]:
    import pymupdf

    pages = _parse_pages(specification)
    output.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    with pymupdf.open(pdf) as document:
        for number in pages:
            if not 1 <= number <= document.page_count:
                raise ValueError(f"PDF page is out of range: {number}")
            destination = output / f"page_{number:04d}.png"
            document[number - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(
                destination
            )
            rendered.append(destination)
    return rendered


def _parse_pages(specification: str) -> list[int]:
    pages: set[int] = set()
    for part in specification.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"invalid descending page range: {part}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    if not pages or min(pages) < 1:
        raise ValueError(f"invalid page selection: {specification}")
    return sorted(pages)


def _validate_excerpts(proposal: dict[str, Any], paper_dir: Path) -> None:
    cached: dict[str, str] = {}
    for operation in proposal["operations"]:
        for provenance in operation["provenance"]:
            excerpt = provenance.get("excerpt")
            source = provenance["source"]
            if not excerpt or source.startswith("assets/") or source == "paper.pdf":
                continue
            if source not in cached:
                cached[source] = (paper_dir / source).read_text(encoding="utf-8")
            if excerpt not in cached[source]:
                raise ValueError(
                    f"proposal excerpt for {operation['item_id']} was not found in {source}"
                )
