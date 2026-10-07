"""Exact and normalized deduplication utilities."""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Set, Tuple

from .normalize import normalize_text
from .schema import SmsRecord


def deduplicate_exact(records: Sequence[SmsRecord]) -> Tuple[List[SmsRecord], int]:
    """Remove records with duplicate raw text, keeping first occurrence."""
    seen: Set[str] = set()
    kept: List[SmsRecord] = []
    removed = 0
    for record in records:
        if record.text in seen:
            removed += 1
            continue
        seen.add(record.text)
        kept.append(record)
    return kept, removed


def deduplicate_normalized(
    records: Sequence[SmsRecord],
) -> Tuple[List[SmsRecord], int]:
    """Remove records with duplicate normalized text."""
    seen: Set[str] = set()
    kept: List[SmsRecord] = []
    removed = 0
    for record in records:
        key = normalize_text(record.text)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(record)
    return kept, removed


def index_by_id(records: Iterable[SmsRecord]) -> Dict[str, SmsRecord]:
    return {record.id: record for record in records}
