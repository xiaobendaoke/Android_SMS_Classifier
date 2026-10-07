"""Classification metrics utilities."""
from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Sequence, Tuple

import numpy as np

from .schema import LABEL_ORDER

LABELS = list(LABEL_ORDER)


def confusion_matrix(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] = LABELS,
) -> np.ndarray:
    """Compute confusion matrix with fixed label order."""
    index = {label: i for i, label in enumerate(labels)}
    size = len(labels)
    matrix = np.zeros((size, size), dtype=np.int64)
    for truth, pred in zip(y_true, y_pred):
        if truth not in index or pred not in index:
            continue
        matrix[index[truth], index[pred]] += 1
    return matrix


def per_class_prf(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] = LABELS,
) -> Dict[str, Dict[str, float]]:
    """Precision, recall, F1 per class."""
    matrix = confusion_matrix(y_true, y_pred, labels)
    metrics: Dict[str, Dict[str, float]] = {}
    for i, label in enumerate(labels):
        tp = float(matrix[i, i])
        fp = float(matrix[:, i].sum() - tp)
        fn = float(matrix[i, :].sum() - tp)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        metrics[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return metrics


def macro_f1(y_true: Sequence[str], y_pred: Sequence[str]) -> float:
    prf = per_class_prf(y_true, y_pred)
    return float(np.mean([v["f1"] for v in prf.values()]))


def accuracy(y_true: Sequence[str], y_pred: Sequence[str]) -> float:
    if not y_true:
        return 0.0
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / len(y_true)


def label_distribution(labels: Sequence[str]) -> Dict[str, int]:
    return dict(Counter(labels))


def wilson_interval(
    successes: int,
    total: int,
    z: float = 1.96,
) -> Tuple[float, float]:
    """
    Wilson score interval for a binomial proportion.

    Returns (lower, upper) bounds in [0, 1].
    """
    if total <= 0:
        return (0.0, 0.0)
    p_hat = successes / total
    z2 = z * z
    denom = 1.0 + z2 / total
    center = (p_hat + z2 / (2.0 * total)) / denom
    margin = (
        z
        * math.sqrt((p_hat * (1.0 - p_hat) + z2 / (4.0 * total)) / total)
        / denom
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def summarize_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Sequence[str] = LABELS,
) -> Dict[str, object]:
    """Bundle accuracy, macro F1, per-class PRF, and confusion matrix."""
    prf = per_class_prf(y_true, y_pred, labels)
    matrix = confusion_matrix(y_true, y_pred, labels)
    return {
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(y_true, y_pred),
        "per_class": prf,
        "confusion_matrix": matrix.tolist(),
        "label_order": list(labels),
        "count": len(y_true),
    }
