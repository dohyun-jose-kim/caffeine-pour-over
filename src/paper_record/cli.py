from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import display_version
from .canonical import ensure_canonical_scaffold
from .doctor import run_checks
from .ingest import ingest_native
from .manifest import load_manifest
from .reading import read_paper
from .review import apply_review, approve_all, load_proposal, regenerate_item
from .resolution import resolve_unresolved
from .schema import SCHEMAS
from .structured import MinerURunner, ingest_structured, structured_is_identical
from .util import slugify


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paper-record",
        description="Build and maintain three-layer scientific paper records.",
    )
    parser.add_argument("--version", action="version", version=f"paper-record {display_version()}")
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
    read.set_defaults(handler=_read)

    resolve = commands.add_parser("resolve", help="inspect evidence for an unresolved item")
    _add_provider_options(resolve)
    resolve.add_argument("paper_dir", type=Path)
    resolve.add_argument("unresolved_id")
    resolve.add_argument("--pages")
    resolve.add_argument("--assets", nargs="*", default=[])
    resolve.set_defaults(handler=_resolve)

    review = commands.add_parser("review", help="review and apply an LLM proposal")
    review.add_argument("paper_dir", type=Path)
    review.add_argument("--read-id")
    review.add_argument("--approve-all", action="store_true")
    review.add_argument(
        "--decisions", type=Path, help="JSON decision array for noninteractive review"
    )
    _add_provider_options(review)
    review.set_defaults(handler=_review)

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
        ensure_canonical_scaffold(paper_dir)
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


def _read(args: argparse.Namespace) -> int:
    try:
        read_id, proposal = read_paper(
            args.paper_dir,
            provider_name=args.provider,
            model=args.model,
            purpose=args.purpose,
            pages=args.pages,
            assets=args.assets,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"paper-record: read failed: {error}", file=sys.stderr)
        return 1
    print(f"proposal created: {read_id}")
    print(proposal)
    return 0


def _review(args: argparse.Namespace) -> int:
    paper_dir = args.paper_dir.expanduser().resolve()
    try:
        read_id = args.read_id or _latest_read_id(paper_dir)
        _, envelope = load_proposal(paper_dir, read_id)
        print(json.dumps(envelope["proposal"], ensure_ascii=False, indent=2))
        if args.approve_all:
            decisions = approve_all(envelope)
        elif args.decisions:
            decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        elif _yes("Approve the whole proposal? [y/N] "):
            decisions = approve_all(envelope)
        else:
            decisions = _item_review(
                paper_dir, read_id, envelope, provider=args.provider, model=args.model
            )
        accepted = sum(item["decision"] == "ACCEPTED" for item in decisions)
        rejected = sum(item["decision"] == "REJECTED" for item in decisions)
        print(f"Final review summary: accepted={accepted} rejected={rejected}")
        if not args.approve_all and not args.decisions and not _yes("Apply this review? [y/N] "):
            print("review not applied")
            return 0
        path = apply_review(paper_dir, read_id, decisions)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"paper-record: review failed: {error}", file=sys.stderr)
        return 1
    print(f"canonical updated from {read_id}")
    print(path)
    return 0


def _resolve(args: argparse.Namespace) -> int:
    try:
        read_id, proposal = resolve_unresolved(
            args.paper_dir,
            args.unresolved_id,
            pages=args.pages,
            assets=args.assets,
            provider_name=args.provider,
            model=args.model,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"paper-record: resolve failed: {error}", file=sys.stderr)
        return 1
    print(f"resolution proposal created: {read_id}")
    print(proposal)
    return 0


def _latest_read_id(paper_dir: Path) -> str:
    reviews = paper_dir / ".paper-record" / "reviews"
    ids = sorted(
        path.name
        for path in reviews.glob("READ-[0-9][0-9][0-9][0-9]")
        if (path / "proposal.json").exists()
    )
    if not ids:
        raise ValueError("no reading proposal exists")
    return ids[-1]


def _yes(prompt: str) -> bool:
    return input(prompt).strip().lower() in {"y", "yes"}


def _item_review(
    paper_dir: Path,
    read_id: str,
    envelope: dict,
    *,
    provider: str,
    model: str | None,
) -> list[dict[str, str | None]]:
    decisions: list[dict[str, str | None]] = []
    for original in envelope["proposal"]["operations"]:
        item = original
        while True:
            print(json.dumps(item, ensure_ascii=False, indent=2))
            choice = input("Accept, reject, or feedback? [a/r/f] ").strip().lower()
            if choice in {"a", "accept"}:
                decisions.append(
                    {"item_id": item["item_id"], "decision": "ACCEPTED", "feedback": None}
                )
                break
            if choice in {"r", "reject"}:
                decisions.append(
                    {"item_id": item["item_id"], "decision": "REJECTED", "feedback": None}
                )
                break
            if choice in {"f", "feedback"}:
                feedback = input("Feedback for this item: ").strip()
                if not feedback:
                    print("Feedback cannot be empty.")
                    continue
                item = regenerate_item(
                    paper_dir,
                    read_id,
                    item["item_id"],
                    feedback,
                    provider_name=provider,
                    model=model,
                )
                continue
            print("Enter a, r, or f.")
    return decisions


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"paper-record: {args.command} is not implemented yet", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))
