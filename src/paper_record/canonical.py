from __future__ import annotations

from pathlib import Path

from .util import atomic_write_text


CANONICAL_SCAFFOLD = """---
schema_version: 1
record_type: canonical
canonical_version: 0
canonical_language: en
reading_status: NOT_READ
---

> This file is a cumulative LLM reading record. The original PDF remains authoritative.
> Conflicting parser content must remain unresolved or be resolved from original visual evidence.

# Current Canonical Record

## Paper Identity

Not read.

## Canonical Summary

Not read.

## Canonical Structure

Not read.

## Quantitative Claims

None recorded.

## Figures

None visually read.

## Tables

None visually read.

## Equations

None visually read.

## Source Disagreements

None recorded.

## Unresolved Items

None recorded.

## Canonical Notes

<!-- USER_NOTES_START -->
<!-- USER_NOTES_END -->

# Reading Ledger

No reads recorded.
"""


def ensure_canonical_scaffold(paper_dir: Path) -> bool:
    path = paper_dir / "03_canonical.md"
    if path.exists():
        return False
    atomic_write_text(path, CANONICAL_SCAFFOLD)
    return True
