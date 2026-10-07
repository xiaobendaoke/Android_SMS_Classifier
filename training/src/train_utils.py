"""Shared training helpers: seeding, JSONL encoding, label maps."""
from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .byte_encoder import encode_text
from .normalize import normalize_text
from .schema import LABEL_ORDER, SmsRecord, load_jsonl


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass
    try:
        import tensorflow as tf

        tf.random.set_seed(seed)
    except ImportError:
        pass


def balanced_class_weights(
    labels: np.ndarray,
    num_classes: int,
    *,
    multipliers: Optional[Mapping[str, float]] = None,
) -> np.ndarray:
    """Return mean-one inverse-frequency weights with optional label multipliers."""
    counts = np.bincount(labels.astype(np.int64), minlength=num_classes).astype(np.float32)
    counts = np.maximum(counts, 1.0)
    weights = counts.sum() / (num_classes * counts)
    for idx in range(min(num_classes, len(LABEL_ORDER))):
        if multipliers:
            weights[idx] *= float(multipliers.get(LABEL_ORDER[idx], 1.0))
    weights *= num_classes / float(weights.sum())
    return weights.astype(np.float32)


def load_labeled_records(path: Path) -> List[SmsRecord]:
    records = load_jsonl(path)
    return [r for r in records if r.label in LABEL_ORDER]


def filter_records_by_languages(
    records: Sequence[SmsRecord],
    languages: Optional[Sequence[str]],
) -> List[SmsRecord]:
    """Filter records to the explicitly accepted languages; empty means no filter."""
    accepted = {
        str(language).strip().lower()
        for language in (languages or [])
        if str(language).strip()
    }
    if not accepted:
        return list(records)
    return [
        record
        for record in records
        if (record.language or "").strip().lower() in accepted
    ]


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


def split_student_logits(
    logits: np.ndarray,
    num_classes: int = len(LABEL_ORDER),
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """Split the four-class logits from an optional transaction-protection logit."""
    values = np.asarray(logits)
    if values.ndim < 2 or values.shape[-1] < num_classes:
        raise ValueError(
            f"Expected [..., >={num_classes}] student logits, got {values.shape}"
        )
    class_logits = values[..., :num_classes]
    protection_logits = (
        values[..., num_classes]
        if values.shape[-1] > num_classes
        else None
    )
    return class_logits, protection_logits


def student_predictions(
    logits: np.ndarray,
    *,
    num_classes: int = len(LABEL_ORDER),
    transaction_threshold: Optional[float] = None,
) -> np.ndarray:
    """Return class predictions, optionally allowing the auxiliary head to protect transactions."""
    class_logits, protection_logits = split_student_logits(logits, num_classes)
    predictions = np.argmax(class_logits, axis=-1).astype(np.int32)
    if transaction_threshold is not None and protection_logits is not None:
        protection_prob = 1.0 / (1.0 + np.exp(-protection_logits))
        predictions = np.where(
            protection_prob >= float(transaction_threshold),
            LABEL_ORDER.index("TRANSACTION"),
            predictions,
        ).astype(np.int32)
    return predictions


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
