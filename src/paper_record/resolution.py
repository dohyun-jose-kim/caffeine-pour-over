from __future__ import annotations

import json
from pathlib import Path

from .canonical import load_canonical
from .providers import Provider
from .reading import read_paper


def resolve_unresolved(
    paper_dir: Path,
    item_id: str,
    *,
    pages: str | None,
    assets: list[str],
    provider_name: str = "codex",
    model: str | None = None,
    provider: Provider | None = None,
) -> tuple[str, Path]:
    paper_dir = paper_dir.expanduser().resolve()
    if not pages and not assets:
        raise ValueError("resolve requires explicit --pages and/or --assets visual evidence")
    state, _ = load_canonical(paper_dir / "03_canonical.md")
    matches = [item for item in state["unresolved"] if item.get("item_id") == item_id]
    if not matches:
        raise ValueError(f"canonical unresolved item does not exist: {item_id}")
    purpose = " ".join(
        [
            f"Resolve only canonical unresolved item {item_id} using the explicitly supplied visual evidence.",
            "If the evidence is insufficient, keep it UNRESOLVED; never infer source confirmation from text agreement.",
            f"Current item: {json.dumps(matches[0], ensure_ascii=False)}",
        ]
    )
    return read_paper(
        paper_dir,
        provider_name=provider_name,
        model=model,
        purpose=purpose,
        pages=pages,
        assets=assets,
        provider=provider,
    )
