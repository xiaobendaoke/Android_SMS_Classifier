"""Detect train/validation/test group leakage."""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Set, Tuple

from .schema import SmsRecord
from .split_groups import group_key


def collect_split_ids(records: Sequence[SmsRecord]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {"train": set(), "validation": set(), "test": set()}
    for record in records:
        split = record.split if record.split in out else "train"
        out[split].add(record.id)
    return out


def collect_split_groups(records: Sequence[SmsRecord]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {"train": set(), "validation": set(), "test": set()}
    for record in records:
        split = record.split if record.split in out else "train"
        out[split].add(group_key(record))
    return out


def detect_id_overlap(split_ids: Dict[str, Set[str]]) -> List[Dict[str, object]]:
    issues: List[Dict[str, object]] = []
    pairs = (("train", "validation"), ("train", "test"), ("validation", "test"))
    for left, right in pairs:
        overlap = sorted(split_ids.get(left, set()) & split_ids.get(right, set()))
        if overlap:
            issues.append(
                {
                    "type": "id_overlap",
                    "splits": [left, right],
                    "count": len(overlap),
                    "examples": overlap[:10],
                }
            )
    return issues


def detect_group_leakage(split_groups: Dict[str, Set[str]]) -> List[Dict[str, object]]:
    issues: List[Dict[str, object]] = []
    pairs = (("train", "validation"), ("train", "test"), ("validation", "test"))
    for left, right in pairs:
        overlap = sorted(split_groups.get(left, set()) & split_groups.get(right, set()))
        if overlap:
            issues.append(
                {
                    "type": "template_sender_group_leak",
                    "splits": [left, right],
                    "count": len(overlap),
                    "examples": overlap[:10],
                }
            )
    return issues


def detect_parent_leakage(records: Sequence[SmsRecord]) -> List[Dict[str, object]]:
    """Flag adversarial/augmented children whose parent lives in another split."""
    by_id = {r.id: r for r in records}
    issues: List[Dict[str, object]] = []
    examples: List[Dict[str, str]] = []
    for record in records:
        if not record.parent_id:
            continue
        parent = by_id.get(record.parent_id)
        if parent is None:
            continue
        if parent.split != record.split and record.split == "test":
            examples.append(
                {
                    "child_id": record.id,
                    "parent_id": parent.id,
                    "child_split": record.split,
                    "parent_split": parent.split,
                }
            )
    if examples:
        issues.append(
            {
                "type": "parent_in_other_split",
                "count": len(examples),
                "examples": examples[:10],
            }
        )
    return issues


def audit_leakage(records: Sequence[SmsRecord]) -> Dict[str, object]:
    split_ids = collect_split_ids(records)
    split_groups = collect_split_groups(records)
    issues = (
        detect_id_overlap(split_ids)
        + detect_group_leakage(split_groups)
        + detect_parent_leakage(records)
    )
    return {
        "status": "PASS" if not issues else "FAIL",
        "issue_count": len(issues),
        "issues": issues,
        "split_counts": {k: len(v) for k, v in split_ids.items()},
        "group_counts": {k: len(v) for k, v in split_groups.items()},
    }
