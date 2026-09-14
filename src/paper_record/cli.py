from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .doctor import run_checks
from .schema import SCHEMAS


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
    ingest.set_defaults(handler=_not_implemented)

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
    status.set_defaults(handler=_not_implemented)
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


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"paper-record: {args.command} is not implemented yet", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))
