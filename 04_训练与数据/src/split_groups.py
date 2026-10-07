"""Leakage-safe connected-component train/validation/test splitting."""
from __future__ import annotations

import hashlib
import random
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from .normalize import normalize_text
from .schema import SmsRecord

DEFAULT_SPLITS = ("train", "validation", "test")
DEFAULT_RATIOS = (0.8, 0.1, 0.1)


def group_key(record: SmsRecord) -> str:
    """Legacy display key; splitting uses connected components, not this pair."""
    return f"{record.template_group}::{record.sender_group}"


def template_fingerprint(text: str) -> str:
    """Stable template fingerprint with volatile URLs/codes/numbers masked."""
    normalized = normalize_text(text).lower()
    normalized = re.sub(r"https?://\S+|www\.\S+", "<url>", normalized)
    normalized = re.sub(r"\b[a-z0-9]{6,}\b", "<token>", normalized)
    normalized = re.sub(r"\d+(?:[.,]\d+)*", "<num>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def record_group_tokens(record: SmsRecord) -> Iterable[str]:
    """Identifiers whose equality must force records into the same split."""
    yield f"template:{record.template_group}"
    yield f"sender:{record.sender_group}"
    yield f"fingerprint:{template_fingerprint(record.text)}"
    # A parent and all of its children share the parent's family token.
    yield f"family:{record.id}"
    if record.parent_id:
        yield f"family:{record.parent_id}"


def connected_group_ids(records: Sequence[SmsRecord]) -> Dict[int, str]:
    """Return deterministic component IDs keyed by record index."""
    union_find = _UnionFind(len(records))
    first_by_token: Dict[str, int] = {}
    for idx, record in enumerate(records):
        for token in record_group_tokens(record):
            first = first_by_token.setdefault(token, idx)
            union_find.union(idx, first)

    members: Dict[int, List[int]] = defaultdict(list)
    for idx in range(len(records)):
        members[union_find.find(idx)].append(idx)

    component_ids: Dict[int, str] = {}
    for indices in members.values():
        signatures = sorted(
            f"{records[idx].id}\0{records[idx].template_group}\0"
            f"{records[idx].sender_group}\0{template_fingerprint(records[idx].text)}"
            for idx in indices
        )
        digest = hashlib.sha256("\n".join(signatures).encode("utf-8")).hexdigest()[:20]
        component_id = f"cc-{digest}"
        for idx in indices:
            component_ids[idx] = component_id
    return component_ids


def group_records(records: Sequence[SmsRecord]) -> Dict[str, List[SmsRecord]]:
    """Group records by the transitive closure of all leakage identities."""
    groups: Dict[str, List[SmsRecord]] = defaultdict(list)
    component_ids = connected_group_ids(records)
    for idx, record in enumerate(records):
        groups[component_ids[idx]].append(record)
    return dict(groups)


def _assignment_cost(
    counts: Dict[str, int],
    label_counts: Dict[str, Dict[str, int]],
    targets: Dict[str, float],
    label_targets: Dict[str, Dict[str, float]],
) -> float:
    cost = 0.0
    for split_name in DEFAULT_SPLITS:
        target = max(targets[split_name], 1.0)
        cost += (counts[split_name] - target) ** 2 / target
        for label, label_target in label_targets[split_name].items():
            denom = max(label_target, 1.0)
            cost += 1.5 * (label_counts[split_name][label] - label_target) ** 2 / denom
    return cost


def split_groups(
    records: Sequence[SmsRecord],
    ratios: Tuple[float, float, float] = DEFAULT_RATIOS,
    seed: int = 42,
) -> Dict[str, List[SmsRecord]]:
    """
    Split connected components so template, sender, parent family, and stable
    text fingerprint can never cross splits. Components are greedily assigned
    to keep both total size and label distribution close to requested ratios.

    Returns dict with keys train, validation, test.
    """
    if abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError("ratios must sum to 1.0")
    groups = group_records(records)
    group_ids = sorted(groups)
    rng = random.Random(seed)
    rng.shuffle(group_ids)
    tie_break = {gid: idx for idx, gid in enumerate(group_ids)}
    group_ids.sort(key=lambda gid: (-len(groups[gid]), tie_break[gid]))

    total = len(records)
    labels = sorted({record.label for record in records})
    total_by_label = {
        label: sum(1 for record in records if record.label == label) for label in labels
    }
    targets = {
        split_name: total * ratios[idx] for idx, split_name in enumerate(DEFAULT_SPLITS)
    }
    label_targets = {
        split_name: {
            label: total_by_label[label] * ratios[idx] for label in labels
        }
        for idx, split_name in enumerate(DEFAULT_SPLITS)
    }
    counts = {split_name: 0 for split_name in DEFAULT_SPLITS}
    label_counts = {
        split_name: {label: 0 for label in labels} for split_name in DEFAULT_SPLITS
    }
    split_map: Dict[str, List[str]] = {name: [] for name in DEFAULT_SPLITS}

    for gid in group_ids:
        group = groups[gid]
        group_labels = {
            label: sum(1 for record in group if record.label == label) for label in labels
        }
        best_split = None
        best_cost = None
        for split_name in DEFAULT_SPLITS:
            counts[split_name] += len(group)
            for label, value in group_labels.items():
                label_counts[split_name][label] += value
            cost = _assignment_cost(counts, label_counts, targets, label_targets)
            counts[split_name] -= len(group)
            for label, value in group_labels.items():
                label_counts[split_name][label] -= value
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_split = split_name

        assert best_split is not None
        split_map[best_split].append(gid)
        counts[best_split] += len(group)
        for label, value in group_labels.items():
            label_counts[best_split][label] += value

    result: Dict[str, List[SmsRecord]] = {name: [] for name in DEFAULT_SPLITS}
    for split_name, ids in split_map.items():
        for gid in ids:
            for record in groups[gid]:
                result[split_name].append(
                    SmsRecord(**{**record.to_dict(), "split": split_name})
                )
    return result
