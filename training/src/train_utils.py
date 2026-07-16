"""Shared training helpers: seeding, JSONL encoding, label maps."""
from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .byte_encoder import encode_text
from .normalize import normalize_text
from .schema import LABEL_ORDER, SmsRecord, load_jsonl


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import tensorflow as tf

        tf.random.set_seed(seed)
    except ImportError:
        pass


def load_labeled_records(path: Path) -> List[SmsRecord]:
    records = load_jsonl(path)
    return [r for r in records if r.label in LABEL_ORDER]


def records_to_xy(
    records: Sequence[SmsRecord],
    *,
    max_bytes: int = 512,
) -> Tuple[np.ndarray, np.ndarray]:
    xs: List[List[int]] = []
    ys: List[int] = []
    label_to_idx = {label: i for i, label in enumerate(LABEL_ORDER)}
    for record in records:
        text = normalize_text(record.text)
        xs.append(encode_text(text, length=max_bytes))
        ys.append(label_to_idx[record.label])
    return np.asarray(xs, dtype=np.int32), np.asarray(ys, dtype=np.int32)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def softmax_np(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=-1, keepdims=True)


def one_hot(indices: np.ndarray, num_classes: int) -> np.ndarray:
    out = np.zeros((len(indices), num_classes), dtype=np.float32)
    out[np.arange(len(indices)), indices] = 1.0
    return out


def iter_jsonl_texts(path: Path, limit: Optional[int] = None) -> Iterable[str]:
    count = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            yield str(row.get("text", ""))
            count += 1
            if limit is not None and count >= limit:
                break
