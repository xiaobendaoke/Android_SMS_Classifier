"""Detect train/validation/test leakage across connected grouping identities."""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Sequence, Set

from .schema import SmsRecord
from .split_groups import connected_group_ids, template_fingerprint


def collect_split_ids(records: Sequence[SmsRecord]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {"train": set(), "validation": set(), "test": set()}
    for record in records:
        split = record.split if record.split in out else "train"
        out[split].add(record.id)
    return out


def collect_split_groups(records: Sequence[SmsRecord]) -> Dict[str, Set[str]]:
    """Collect connected-component IDs per split."""
    out: Dict[str, Set[str]] = {"train": set(), "validation": set(), "test": set()}
    component_ids = connected_group_ids(records)
    for idx, record in enumerate(records):
        split = record.split if record.split in out else "train"
        out[split].add(component_ids[idx])
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
                    "type": "connected_component_leak",
                    "splits": [left, right],
                    "count": len(overlap),
                    "examples": overlap[:10],
                }
            )
    return issues


def detect_identity_leakage(
    records: Sequence[SmsRecord],
    *,
    identity_name: str,
    identity: Callable[[SmsRecord], str],
) -> List[Dict[str, object]]:
    """Report any template/sender/fingerprint identity spanning splits."""
    splits_by_identity: Dict[str, Set[str]] = defaultdict(set)
    for record in records:
        value = identity(record)
        if value:
            splits_by_identity[value].add(record.split)
    leaked = sorted(
        value for value, splits in splits_by_identity.items() if len(splits) > 1
    )
    if not leaked:
        return []
    return [
        {
            "type": f"{identity_name}_leak",
            "count": len(leaked),
            "examples": leaked[:10],
        }
    ]


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
        if parent.split != record.split:
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
        + detect_identity_leakage(
            records,
            identity_name="template_group",
            identity=lambda record: record.template_group,
        )
        + detect_identity_leakage(
            records,
            identity_name="sender_group",
            identity=lambda record: record.sender_group,
        )
        + detect_identity_leakage(
            records,
            identity_name="template_fingerprint",
            identity=lambda record: template_fingerprint(record.text),
        )
        + detect_parent_leakage(records)
    )
    return {
        "status": "PASS" if not issues else "FAIL",
        "issue_count": len(issues),
        "issues": issues,
        "split_counts": {k: len(v) for k, v in split_ids.items()},
        "connected_component_counts": {k: len(v) for k, v in split_groups.items()},
    }
