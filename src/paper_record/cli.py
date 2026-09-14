from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .doctor import run_checks
from .ingest import ingest_native
from .manifest import load_manifest
from .schema import SCHEMAS
from .structured import MinerURunner, ingest_structured, structured_is_identical
from .util import slugify


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-record",
        description="Build and maintain three-layer scientific paper records.",
    )
    parser.add_argument("--version", action="version", version=f"paper-record {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="check local parser and LLM prerequisites")
    doctor.add_argument("--root", type=Path, default=Path("papers"))
    doctor.set_defaults(handler=_doctor)

    schema = commands.add_parser("schema", help="print a versioned JSON schema")
    schema.add_argument("name", choices=sorted(SCHEMAS))
    schema.set_defaults(handler=_schema)

    ingest = commands.add_parser("ingest", help="create 01_native.md and 02_structured.md")
    ingest.add_argument("pdf", type=Path)
    ingest.add_argument("--id", dest="paper_id")
    ingest.add_argument("--root", type=Path, default=Path("papers"))
    ingest.set_defaults(handler=_ingest)

    read = commands.add_parser("read", help="ask an LLM for a canonical reading proposal")
    _add_provider_options(read)
    read.add_argument("paper_dir", type=Path)
    read.add_argument("--purpose", default="Initial full-paper reading")
    read.add_argument("--pages")
    read.add_argument("--assets", nargs="*", default=[])
    read.set_defaults(handler=_not_implemented)

    resolve = commands.add_parser("resolve", help="inspect evidence for an unresolved item")
    _add_provider_options(resolve)
    resolve.add_argument("paper_dir", type=Path)
    resolve.add_argument("unresolved_id")
    resolve.set_defaults(handler=_not_implemented)

    review = commands.add_parser("review", help="review and apply an LLM proposal")
    review.add_argument("paper_dir", type=Path)
    review.add_argument("--read-id")
    review.set_defaults(handler=_not_implemented)

    status = commands.add_parser("status", help="show parser, revision, and canonical status")
    status.add_argument("paper_dir", type=Path)
    status.set_defaults(handler=_status)
    return parser


def _add_provider_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=("codex", "claude"), default="codex")
    parser.add_argument("--model")


def _doctor(args: argparse.Namespace) -> int:
    checks = run_checks(args.root)
    for check in checks:
        print(f"{check.state:4}  {check.name:16} {check.detail}")
    return 1 if any(check.required and check.state == "FAIL" for check in checks) else 0


def _schema(args: argparse.Namespace) -> int:
    print(json.dumps(SCHEMAS[args.name], ensure_ascii=False, indent=2))
    return 0


def _ingest(args: argparse.Namespace) -> int:
    try:
        runner = MinerURunner()
        current_id = slugify(args.paper_id or args.pdf.stem)
        current = load_manifest(args.root.expanduser().resolve() / current_id)
        force_new = bool(current and current.get("revision_status") == "COMPLETE" and not structured_is_identical(current, runner))
        paper_dir, manifest, native_changed = ingest_native(
            args.pdf, args.root, args.paper_id, force_new=force_new
        )
        manifest, structured_changed = ingest_structured(paper_dir, runner)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"paper-record: ingest failed: {error}", file=sys.stderr)
        return 1
    action = "created" if native_changed or structured_changed else "unchanged"
    print(f"{action}: {paper_dir}")
    print(
        f"revision={manifest['active_revision']} status={manifest['revision_status']} "
        f"native={manifest['parsers']['native']['status']} "
        f"structured={manifest['parsers']['structured']['status']}"
    )
    return 0


def _status(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.paper_dir.expanduser().resolve())
    if manifest is None:
        print(f"paper-record: no manifest in {args.paper_dir}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"paper-record: {args.command} is not implemented yet", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))
