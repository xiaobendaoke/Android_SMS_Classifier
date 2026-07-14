#!/usr/bin/env python3
"""Train n-gram logistic regression baseline (numpy-only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

SEED = 42

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
from src.metrics import summarize_metrics, wilson_interval  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import LABEL_ORDER, load_jsonl  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train byte n-gram logistic baseline (pure numpy)."
    )
    parser.add_argument(
        "--train",
        type=Path,
        default=ROOT / "data" / "processed" / "train.jsonl",
        help="Training JSONL manifest.",
    )
    parser.add_argument(
        "--validation",
        type=Path,
        default=ROOT / "data" / "processed" / "validation.jsonl",
        help="Validation JSONL manifest.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "baseline",
        help="Output directory for baseline model artifacts.",
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "baseline.json",
        help="Metrics JSON output path.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    parser.add_argument("--epochs", type=int, default=200, help="Training epochs.")
    parser.add_argument("--lr", type=float, default=0.1, help="Learning rate.")
    return parser


def byte_ngrams(text: str, ns: Sequence[int] = (2, 3)) -> List[str]:
    data = text.encode("utf-8")
    grams: List[str] = []
    for n in ns:
        for i in range(len(data) - n + 1):
            grams.append(data[i : i + n].hex())
    return grams


def build_vocab(texts: Sequence[str], max_features: int = 4096) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for text in texts:
        for gram in byte_ngrams(normalize_text(text)):
            counts[gram] = counts.get(gram, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    vocab = {gram: idx for idx, (gram, _) in enumerate(ranked[:max_features])}
    return vocab


def vectorize(text: str, vocab: Dict[str, int]) -> np.ndarray:
    vec = np.zeros(len(vocab), dtype=np.float64)
    for gram in byte_ngrams(normalize_text(text)):
        idx = vocab.get(gram)
        if idx is not None:
            vec[idx] += 1.0
    return vec


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    exp = np.exp(shifted)
    return exp / np.sum(exp)


def one_hot(index: int, num_classes: int) -> np.ndarray:
    vec = np.zeros(num_classes, dtype=np.float64)
    vec[index] = 1.0
    return vec


def train_logistic(
    x_train: np.ndarray,
    y_train: np.ndarray,
    num_classes: int,
    epochs: int,
    lr: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n_features = x_train.shape[1]
    weights = rng.normal(0, 0.01, size=(n_features, num_classes))
    bias = np.zeros(num_classes, dtype=np.float64)

    for _ in range(epochs):
        logits = x_train @ weights + bias
        probs = np.array([softmax(row) for row in logits])
        grad_logits = (probs - y_train) / len(x_train)
        grad_w = x_train.T @ grad_logits
        grad_b = np.sum(grad_logits, axis=0)
        weights -= lr * grad_w
        bias -= lr * grad_b

    return np.vstack([weights, bias.reshape(1, -1)])


def predict(params: np.ndarray, x: np.ndarray) -> np.ndarray:
    weights = params[:-1]
    bias = params[-1]
    logits = x @ weights + bias
    return np.array([np.argmax(row) for row in logits])


def frequency_baseline_predict(texts: Sequence[str], label_order: List[str]) -> List[str]:
    """Fallback keyword scorer when training set is empty."""
    keywords = {
        "TRANSACTION": ["入账", "payment", "pembayaran", "भुगतान", "订单", "flight", "shipped"],
        "AD": ["优惠", "promo", "diskon", "click", "prize", "sale", "इनाम", "gratis"],
        "HARASS": ["还钱", "pay me", "utang", "परेशान", "abai", "contact"],
        "FRAUD": ["异常", "verify", "http", "blocked", "diblokir", "ब्लॉक", "phish", "OTP"],
    }
    preds: List[str] = []
    for text in texts:
        norm = normalize_text(text).lower()
        scores = {label: 0 for label in label_order}
        for label, words in keywords.items():
            for word in words:
                if word.lower() in norm:
                    scores[label] += 1
        best = max(label_order, key=lambda lbl: scores[lbl])
        preds.append(best if scores[best] > 0 else label_order[0])
    return preds


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.train.exists():
        print(f"Training data missing: {args.train}", file=sys.stderr)
        return 1

    label_order = list(LABEL_ORDER)
    label_to_idx = {label: i for i, label in enumerate(label_order)}

    train_records = load_jsonl(args.train)
    val_records = load_jsonl(args.validation) if args.validation.exists() else []

    train_texts = [r.text for r in train_records]
    train_labels = [r.label for r in train_records if r.label in label_to_idx]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)

    model_type = "byte_ngram_logistic_numpy"
    params_path = args.output_dir / "baseline_params.npy"

    if len(train_records) < 2 or len(set(train_labels)) < 1:
        print("Insufficient training data; using frequency baseline.", file=sys.stderr)
        model_type = "frequency_keyword_baseline"
        val_true = [r.label for r in val_records if r.label in label_to_idx]
        val_pred = frequency_baseline_predict(
            [r.text for r in val_records], label_order
        )
    else:
        vocab = build_vocab(train_texts)
        if not vocab:
            print("Empty vocabulary; using frequency baseline.", file=sys.stderr)
            model_type = "frequency_keyword_baseline"
            val_true = [r.label for r in val_records if r.label in label_to_idx]
            val_pred = frequency_baseline_predict(
                [r.text for r in val_records], label_order
            )
        else:
            x_train = np.vstack([vectorize(t, vocab) for t in train_texts])
            y_train = np.vstack(
                [
                    one_hot(label_to_idx[r.label], len(label_order))
                    for r in train_records
                    if r.label in label_to_idx
                ]
            )
            params = train_logistic(
                x_train,
                y_train,
                len(label_order),
                epochs=args.epochs,
                lr=args.lr,
                seed=args.seed,
            )
            np.save(params_path, params)
            meta = {
                "vocab": vocab,
                "label_order": label_order,
                "model_type": model_type,
            }
            (args.output_dir / "baseline_meta.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )

            if val_records:
                x_val = np.vstack([vectorize(r.text, vocab) for r in val_records])
                idx_pred = predict(params, x_val)
                val_pred = [label_order[i] for i in idx_pred]
                val_true = [r.label for r in val_records]
            else:
                val_true, val_pred = [], []

    metrics: Dict[str, object] = {
        "seed": args.seed,
        "model_type": model_type,
        "train_count": len(train_records),
        "validation_count": len(val_records),
    }

    if val_true:
        summary = summarize_metrics(val_true, val_pred, label_order)
        txn_idx = label_order.index("TRANSACTION")
        matrix = np.array(summary["confusion_matrix"])
        txn_tp = int(matrix[txn_idx, txn_idx])
        txn_total = int(matrix[txn_idx, :].sum())
        metrics["validation"] = summary
        metrics["transaction_recall"] = summary["per_class"]["TRANSACTION"]["recall"]
        metrics["transaction_recall_ci95"] = wilson_interval(txn_tp, txn_total)
        metrics["macro_f1"] = summary["macro_f1"]
    else:
        metrics["note"] = "no validation split available"

    args.metrics_output.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote metrics to {args.metrics_output}")
    if model_type == "byte_ngram_logistic_numpy":
        print(f"Wrote model params to {params_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
