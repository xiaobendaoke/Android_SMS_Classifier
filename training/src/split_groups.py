"""Group-aware train/validation/test splitting."""
from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from .schema import SmsRecord

DEFAULT_SPLITS = ("train", "validation", "test")
DEFAULT_RATIOS = (0.8, 0.1, 0.1)


def group_key(record: SmsRecord) -> str:
    """Composite key so template_group and sender_group never leak across splits."""
    return f"{record.template_group}::{record.sender_group}"


def group_records(records: Sequence[SmsRecord]) -> Dict[str, List[SmsRecord]]:
    """Group records by template_group + sender_group."""
    groups: Dict[str, List[SmsRecord]] = defaultdict(list)
    for record in records:
        groups[group_key(record)].append(record)
    return dict(groups)


def split_groups(
    records: Sequence[SmsRecord],
    ratios: Tuple[float, float, float] = DEFAULT_RATIOS,
    seed: int = 42,
) -> Dict[str, List[SmsRecord]]:
    """
    Split by (template_group, sender_group) so no group spans multiple splits.

    Returns dict with keys train, validation, test.
    """
    if abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError("ratios must sum to 1.0")
    groups = group_records(records)
    group_ids = sorted(groups.keys())
    rng = random.Random(seed)
    rng.shuffle(group_ids)

    n = len(group_ids)
    train_end = int(n * ratios[0])
    val_end = train_end + int(n * ratios[1])

    split_map = {
        "train": group_ids[:train_end],
        "validation": group_ids[train_end:val_end],
        "test": group_ids[val_end:],
    }

    result: Dict[str, List[SmsRecord]] = {name: [] for name in DEFAULT_SPLITS}
    for split_name, ids in split_map.items():
        for gid in ids:
            for record in groups[gid]:
                result[split_name].append(
                    SmsRecord(**{**record.to_dict(), "split": split_name})
                )
    return result
