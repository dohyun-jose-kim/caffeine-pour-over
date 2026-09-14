from __future__ import annotations

import importlib.metadata
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

from .audit import AuditLog
from .manifest import activate_revision, load_manifest, write_manifest
from .util import atomic_write_text, sha256_file, sha256_text, utc_now


STRUCTURED_OPTIONS = {
    "adapter_revision": 1,
    "backend": "hybrid-engine",
    "effort": "high",
    "method": "auto",
    "formula": True,
    "table": True,
    "image_analysis": False,
}


class StructuredRunner(Protocol):
    version: str

    def run(self, pdf: Path, output: Path) -> None: ...


class MinerURunner:
    @property
    def version(self) -> str:
        try:
            return importlib.metadata.version("mineru")
        except importlib.metadata.PackageNotFoundError:
            return "unavailable"

    def run(self, pdf: Path, output: Path) -> None:
        command = [
            "mineru",
            "-p",
            str(pdf),
            "-o",
            str(output),
            "-b",
            "hybrid-engine",
            "--effort",
            "high",
            "-m",
            "auto",
            "--formula",
            "true",
            "--table",
            "true",
            "--image-analysis",
            "false",
        ]
        try:
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
        except FileNotFoundError as error:
            raise RuntimeError(
                "MinerU is not installed; run `uv sync --extra mineru` and retry"
            ) from error
        if completed.returncode:
            detail = (completed.stderr or completed.stdout).strip()[-4000:]
            raise RuntimeError(f"MinerU failed with exit {completed.returncode}: {detail}")


def structured_identity(runner: StructuredRunner) -> dict[str, Any]:
    return {"name": "mineru", "version": runner.version, "options": STRUCTURED_OPTIONS}


def structured_is_identical(manifest: dict[str, Any], runner: StructuredRunner) -> bool:
    structured = manifest.get("parsers", {}).get("structured", {})
    identity = structured_identity(runner)
    return (
        structured.get("status") == "SUCCEEDED"
        and structured.get("name") == identity["name"]
        and structured.get("version") == identity["version"]
        and structured.get("options") == identity["options"]
    )


def ingest_structured(
    paper_dir: Path, runner: StructuredRunner | None = None
) -> tuple[dict[str, Any], bool]:
    implementation = runner or MinerURunner()
    manifest = load_manifest(paper_dir)
    if manifest is None:
        raise RuntimeError("native manifest is missing")
    native = manifest.get("parsers", {}).get("native", {})
    if native.get("status") != "SUCCEEDED":
        raise RuntimeError("native extraction must succeed before structured extraction")
    if structured_is_identical(manifest, implementation):
        return manifest, False

    revision = manifest["active_revision"]
    revision_dir = paper_dir / ".paper-record" / "revisions" / revision
    log = AuditLog(paper_dir, "ingest")
    identity = structured_identity(implementation)
    manifest["parsers"]["structured"] = {
        **identity,
        "status": "RUNNING",
        "started_at": utc_now(),
    }
    write_manifest(revision_dir, manifest)
    log.event("STAGE_STARTED", "RUNNING", revision=revision, stage="structured")

    try:
        with tempfile.TemporaryDirectory(
            prefix="paper-record-mineru-", dir=paper_dir / ".paper-record"
        ) as temporary:
            raw = Path(temporary) / "output"
            raw.mkdir()
            implementation.run(revision_dir / "paper.pdf", raw)
            markdown, assets = normalize_output(
                raw, revision_dir / "paper.pdf", revision_dir, implementation.version
            )
            atomic_write_text(revision_dir / "02_structured.md", markdown)
            preserved = revision_dir / "mineru_raw"
            if preserved.exists():
                shutil.rmtree(preserved)
            shutil.copytree(raw, preserved)

        manifest["assets"] = assets
        manifest["parsers"]["structured"].update(
            {
                "status": "SUCCEEDED",
                "completed_at": utc_now(),
                "output_sha256": sha256_text(markdown),
            }
        )
        manifest["revision_status"] = "COMPLETE"
        write_manifest(revision_dir, manifest)
        activate_revision(paper_dir, revision)
        log.event(
            "STAGE_SUCCEEDED",
            "SUCCEEDED",
            revision=revision,
            stage="structured",
            asset_count=len(assets),
        )
        return manifest, True
    except BaseException as error:
        manifest["parsers"]["structured"].update(
            {"status": "FAILED", "completed_at": utc_now(), "error": str(error)}
        )
        manifest["revision_status"] = "INCOMPLETE"
        write_manifest(revision_dir, manifest)
        log.event(
            "STAGE_FAILED", "FAILED", revision=revision, stage="structured", error=str(error)
        )
        raise


def normalize_output(
    raw: Path, pdf: Path, revision_dir: Path, parser_version: str
) -> tuple[str, list[dict[str, Any]]]:
    markdown_path = _choose_markdown(raw)
    content_path = _choose_content_list(raw)
    markdown = markdown_path.read_text(encoding="utf-8")
    entries = _load_entries(content_path) if content_path else []
    asset_root = revision_dir / "assets"
    assets, replacements = _materialize_assets(entries, raw, pdf, asset_root)
    for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        markdown = markdown.replace(old, new)

    header = [
        "---",
        "schema_version: 1",
        "record_type: structured",
        f"source_revision: {revision_dir.name}",
        "parser: mineru",
        f"parser_version: {parser_version}",
        "backend: hybrid-engine",
        "effort: high",
        "image_analysis: false",
        "---",
        "",
    ]
    index = ["", "## Paper Record Asset Index", ""]
    if not assets:
        index.append("No visual assets were reported by MinerU.")
    for asset in assets:
        index.extend(
            [
                f"### {asset['id']}",
                "",
                f"- Type: {asset['type']}",
                f"- Page: {asset.get('page') or 'unknown'}",
                f"- Bounding box: {json.dumps(asset.get('bbox'))}",
                f"- Status: {asset['status']}",
                f"- Evidence: `{asset.get('path') or 'missing'}`",
                "",
            ]
        )
    return "\n".join(header) + markdown.rstrip() + "\n" + "\n".join(index).rstrip() + "\n", assets


def _choose_markdown(raw: Path) -> Path:
    candidates = [path for path in raw.rglob("*.md") if path.is_file()]
    if not candidates:
        raise RuntimeError("MinerU produced no Markdown file")
    return max(candidates, key=lambda path: path.stat().st_size)


def _choose_content_list(raw: Path) -> Path | None:
    legacy = list(raw.rglob("*_content_list.json"))
    if legacy:
        return max(legacy, key=lambda path: path.stat().st_size)
    versioned = list(raw.rglob("*content_list_v2.json"))
    return max(versioned, key=lambda path: path.stat().st_size) if versioned else None


def _load_entries(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = []
    if isinstance(data, list):
        for page_index, item in enumerate(data):
            if isinstance(item, list):
                for child in item:
                    if isinstance(child, dict):
                        child = dict(child)
                        child.setdefault("page_idx", page_index)
                        entries.append(child)
            elif isinstance(item, dict):
                entries.append(item)
    return entries


def _materialize_assets(
    entries: list[dict[str, Any]], raw: Path, pdf: Path, asset_root: Path
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    counters = {"figure": 0, "table": 0, "equation": 0}
    assets: list[dict[str, Any]] = []
    replacements: dict[str, str] = {}
    for entry in entries:
        kind = _asset_kind(str(entry.get("type", "")))
        if not kind:
            continue
        counters[kind] += 1
        prefix = {"figure": "FIG", "table": "TABLE", "equation": "EQ"}[kind]
        stem = {"figure": "fig", "table": "table", "equation": "eq"}[kind]
        item_id = f"{prefix}-{counters[kind]:04d}"
        destination = asset_root / f"{kind}s" / f"{stem}_{counters[kind]:03d}.png"
        source_name = _find_image_path(entry)
        page = _page_number(entry)
        bbox = entry.get("bbox")
        status = "MISSING"
        if source_name:
            source = _resolve_asset(raw, source_name)
            if source:
                _convert_to_png(source, destination)
                status = "PRESERVED"
                replacements[source_name] = destination.relative_to(revision_dir(asset_root)).as_posix()
                replacements[Path(source_name).name] = replacements[source_name]
        if status == "MISSING" and kind in {"table", "equation"} and page and bbox:
            if _crop_pdf(pdf, page, bbox, destination):
                status = "CROPPED_FROM_SOURCE"
        relative = destination.relative_to(revision_dir(asset_root)).as_posix() if destination.exists() else None
        assets.append(
            {
                "id": item_id,
                "type": kind,
                "page": page,
                "bbox": bbox,
                "path": relative,
                "sha256": sha256_file(destination) if destination.exists() else None,
                "status": status,
            }
        )
    return assets, replacements


def revision_dir(asset_root: Path) -> Path:
    return asset_root.parent


def _asset_kind(value: str) -> str | None:
    if value in {"image", "chart"}:
        return "figure"
    if value == "table":
        return "table"
    if value in {"equation", "equation_interline", "interline_equation"}:
        return "equation"
    return None


def _page_number(entry: dict[str, Any]) -> int | None:
    value = entry.get("page_idx")
    return int(value) + 1 if isinstance(value, int) else None


def _find_image_path(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("img_path", "image_path"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for child in value.values():
            found = _find_image_path(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_image_path(child)
            if found:
                return found
    return None


def _resolve_asset(raw: Path, name: str) -> Path | None:
    direct = raw / name
    if direct.is_file():
        return direct
    matches = list(raw.rglob(Path(name).name))
    return matches[0] if matches else None


def _convert_to_png(source: Path, destination: Path) -> None:
    import pymupdf

    destination.parent.mkdir(parents=True, exist_ok=True)
    pixmap = pymupdf.Pixmap(str(source))
    pixmap.save(destination)


def _crop_pdf(pdf: Path, page_number: int, bbox: Any, destination: Path) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    import pymupdf

    with pymupdf.open(pdf) as document:
        if not 1 <= page_number <= document.page_count:
            return False
        page = document[page_number - 1]
        values = [float(item) for item in bbox]
        maximum = max(values)
        if maximum <= 1:
            x0, y0, x1, y1 = (
                values[0] * page.rect.width,
                values[1] * page.rect.height,
                values[2] * page.rect.width,
                values[3] * page.rect.height,
            )
        elif maximum <= 1000:
            x0, y0, x1, y1 = (
                values[0] * page.rect.width / 1000,
                values[1] * page.rect.height / 1000,
                values[2] * page.rect.width / 1000,
                values[3] * page.rect.height / 1000,
            )
        else:
            x0, y0, x1, y1 = values
        clip = pymupdf.Rect(x0, y0, x1, y1) & page.rect
        if clip.is_empty:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip, alpha=False).save(destination)
        return True

