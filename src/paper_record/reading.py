from __future__ import annotations

import json
import re
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
    requests, batch_receipts = _reading_requests(
        paper_dir, text_paths, purpose, review_dir, manifest["active_revision"]
    )

    implementation = provider or get_provider(provider_name)
    log.event(
        "COMMAND_STARTED",
        "RUNNING",
        read_id=read_id,
        revision=manifest["active_revision"],
        canonical_version=canonical_state["canonical_version"],
    )
    log.event(
        "LLM_STARTED",
        "RUNNING",
        read_id=read_id,
        provider=implementation.name,
        input_count=len(receipts),
    )
    try:
        results = []
        for index, prompt in enumerate(requests, start=1):
            log.event(
                "STAGE_STARTED",
                "RUNNING",
                read_id=read_id,
                stage="llm_batch",
                batch=index,
                batch_count=len(requests),
            )
            if visual_paths:
                prompt += "\n\nVisual evidence supplied to this read:\n" + "\n".join(
                    f"- {path.relative_to(paper_dir).as_posix()}" for path in visual_paths
                )
            result = implementation.run(
                prompt=prompt,
                schema=PROPOSAL_SCHEMA,
                paper_dir=paper_dir,
                images=visual_paths,
                model=model,
            )
            raw_name = "provider-response.json" if len(requests) == 1 else f"batch-{index:04d}-provider-response.json"
            atomic_write_json(review_dir / raw_name, result.proposal)
            validate_proposal(result.proposal, receipts)
            _validate_excerpts(result.proposal, paper_dir)
            results.append(result)
            log.event(
                "STAGE_SUCCEEDED",
                "SUCCEEDED",
                read_id=read_id,
                stage="llm_batch",
                batch=index,
                batch_count=len(requests),
            )
        result = results[0]
        proposal = _merge_proposals([item.proposal for item in results])
        validate_proposal(proposal, receipts)
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
            "batches": batch_receipts,
            "proposal": proposal,
        }
        atomic_write_json(review_dir / "proposal.json", envelope)
        log.event(
            "PROPOSAL_CREATED",
            "SUCCEEDED",
            read_id=read_id,
            provider=result.provider,
            operation_count=len(proposal["operations"]),
            artifact=str((review_dir / "proposal.json").relative_to(paper_dir)),
        )
        log.event("LLM_COMPLETED", "SUCCEEDED", read_id=read_id, provider=result.provider)
        log.event(
            "COMMAND_COMPLETED",
            "SUCCEEDED",
            read_id=read_id,
            artifact=str((review_dir / "proposal.json").relative_to(paper_dir)),
        )
        return read_id, review_dir / "proposal.json"
    except BaseException as error:
        log.event("LLM_COMPLETED", "FAILED", read_id=read_id, error=str(error))
        log.event("COMMAND_COMPLETED", "FAILED", read_id=read_id, error=str(error))
        raise


def build_prompt(paths: list[Path], purpose: str) -> str:
    return build_prompt_contents([(path.name, path.read_text(encoding="utf-8")) for path in paths], purpose)


def build_prompt_contents(inputs: list[tuple[str, str]], purpose: str) -> str:
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
    for name, content in inputs:
        parts.extend(
            [
                "",
                f"===== BEGIN INPUT: {name} =====",
                content,
                f"===== END INPUT: {name} =====",
            ]
        )
    return "\n".join(parts)


def _reading_requests(
    paper_dir: Path,
    text_paths: list[Path],
    purpose: str,
    review_dir: Path,
    revision: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    complete = build_prompt(text_paths, purpose)
    if len(complete) <= MAX_INPUT_CHARS:
        return [complete], []
    by_name = {path.name: path.read_text(encoding="utf-8") for path in text_paths}
    native_header, native_pages = _split_marked_pages(by_name["01_native.md"])
    structured_header, structured_pages = _split_marked_pages(by_name["02_structured.md"])
    page_numbers = sorted(set(native_pages) | set(structured_pages))
    if not page_numbers:
        raise RuntimeError("long input cannot be batched because page markers are missing")

    def prompt_for(numbers: list[int]) -> str:
        native = native_header + "".join(native_pages.get(number, "") for number in numbers)
        structured = structured_header + "".join(
            structured_pages.get(number, "") for number in numbers
        )
        batch_purpose = f"{purpose}; page-aligned batch {numbers[0]}-{numbers[-1]}"
        return build_prompt_contents(
            [
                ("manifest.yaml", by_name["manifest.yaml"]),
                ("01_native.md", native),
                ("02_structured.md", structured),
                ("03_canonical.md", by_name["03_canonical.md"]),
            ],
            batch_purpose,
        ) + "\nItem IDs must be globally stable and include a page-specific discriminator when needed."

    groups: list[list[int]] = []
    current: list[int] = []
    for number in page_numbers:
        candidate = current + [number]
        if current and len(prompt_for(candidate)) > MAX_INPUT_CHARS:
            groups.append(current)
            current = [number]
        else:
            current = candidate
        if len(prompt_for(current)) > MAX_INPUT_CHARS:
            raise RuntimeError(f"page {number} alone exceeds the safe provider input limit")
    if current:
        groups.append(current)

    requests: list[str] = []
    batch_receipts: list[dict[str, Any]] = []
    for index, numbers in enumerate(groups, start=1):
        batch_dir = review_dir / "inputs" / f"BATCH-{index:04d}"
        batch_dir.mkdir(parents=True)
        native_path = batch_dir / "01_native.md"
        structured_path = batch_dir / "02_structured.md"
        native_text = native_header + "".join(native_pages.get(number, "") for number in numbers)
        structured_text = structured_header + "".join(
            structured_pages.get(number, "") for number in numbers
        )
        native_path.write_text(native_text, encoding="utf-8")
        structured_path.write_text(structured_text, encoding="utf-8")
        input_receipts = [
            _receipt(paper_dir, native_path, "text", revision),
            _receipt(paper_dir, structured_path, "text", revision),
        ]
        batch_receipts.append(
            {
                "batch_id": f"BATCH-{index:04d}",
                "pages": numbers,
                "inputs": input_receipts,
            }
        )
        requests.append(prompt_for(numbers))
    return requests, batch_receipts


def _split_marked_pages(text: str) -> tuple[str, dict[int, str]]:
    matches = list(re.finditer(r"(?m)^<!-- PAGE: (\d+) -->\s*$", text))
    if not matches:
        return text, {}
    header = text[: matches[0].start()]
    pages: dict[int, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pages[int(match.group(1))] = text[match.start() : end]
    return header, pages


def _merge_proposals(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    if len(proposals) == 1:
        return proposals[0]
    operations: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    requests: list[dict[str, Any]] = []
    request_keys: set[str] = set()
    for proposal in proposals:
        for operation in proposal["operations"]:
            item_id = operation["item_id"]
            if item_id in seen and seen[item_id] != operation:
                raise ValueError(f"batch proposals disagree for item_id: {item_id}")
            if item_id not in seen:
                seen[item_id] = operation
                operations.append(operation)
        for request in proposal["evidence_requests"]:
            key = json.dumps(request, sort_keys=True, ensure_ascii=False)
            if key not in request_keys:
                request_keys.add(key)
                requests.append(request)
    return {
        "reading": {
            "purpose": proposals[0]["reading"]["purpose"],
            "result": " ".join(item["reading"]["result"] for item in proposals),
        },
        "operations": operations,
        "evidence_requests": requests,
    }


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
