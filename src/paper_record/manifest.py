from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .util import atomic_write_json, load_yaml_compatible, utc_now


ACTIVE_LINK = Path(".paper-record/active")
PUBLIC_REVISION_LINKS = ("paper.pdf", "manifest.yaml", "01_native.md", "02_structured.md", "assets")


def load_manifest(paper_dir: Path) -> dict[str, Any] | None:
    path = paper_dir / "manifest.yaml"
    return load_yaml_compatible(path) if path.exists() else None


def new_manifest(paper_id: str, revision: str, source: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "paper_id": paper_id,
        "canonical_language": "en",
        "active_revision": revision,
        "revision_status": "INCOMPLETE",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "source": source,
        "parsers": {
            "native": {"status": "PENDING"},
            "structured": {"status": "PENDING"},
        },
        "canonical": {
            "version": 0,
            "based_on_revisions": [],
            "review_required": True,
        },
        "assets": [],
        "warnings": [],
    }


def next_revision(paper_dir: Path) -> str:
    revisions = paper_dir / ".paper-record" / "revisions"
    numbers = []
    if revisions.exists():
        for entry in revisions.iterdir():
            if entry.is_dir() and entry.name.startswith("r") and entry.name[1:].isdigit():
                numbers.append(int(entry.name[1:]))
    return f"r{max(numbers, default=0) + 1:04d}"


def resumable_revision(
    paper_dir: Path, source_sha256: str, parser_version: str, parser_options: dict[str, Any]
) -> tuple[Path, dict[str, Any]] | None:
    revisions = paper_dir / ".paper-record" / "revisions"
    if not revisions.exists():
        return None
    for revision_dir in sorted(revisions.glob("r[0-9][0-9][0-9][0-9]"), reverse=True):
        path = revision_dir / "manifest.yaml"
        if not path.exists():
            continue
        manifest = load_yaml_compatible(path)
        native = manifest.get("parsers", {}).get("native", {})
        if (
            manifest.get("revision_status") == "INCOMPLETE"
            and manifest.get("source", {}).get("sha256") == source_sha256
            and native.get("version") == parser_version
            and native.get("options") == parser_options
            and native.get("status") in {"PENDING", "FAILED"}
        ):
            return revision_dir, manifest
    return None


def write_manifest(revision_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    atomic_write_json(revision_dir / "manifest.yaml", manifest)


def ensure_public_links(paper_dir: Path) -> None:
    for name in PUBLIC_REVISION_LINKS:
        link = paper_dir / name
        if link.is_symlink():
            continue
        if link.exists():
            raise RuntimeError(f"refusing to replace non-symlink public path: {link}")
        link.symlink_to(Path(".paper-record/active") / name, target_is_directory=name == "assets")


def activate_revision(paper_dir: Path, revision: str) -> None:
    internal = paper_dir / ".paper-record"
    target = Path("revisions") / revision
    if not (internal / target / "manifest.yaml").exists():
        raise RuntimeError(f"revision is not publishable: {revision}")
    temporary = internal / ".active.new"
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    temporary.symlink_to(target, target_is_directory=True)
    os.replace(temporary, internal / "active")
    ensure_public_links(paper_dir)
