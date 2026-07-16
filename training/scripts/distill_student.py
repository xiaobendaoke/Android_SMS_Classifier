#!/usr/bin/env python3
"""Distill Byte TextCNN student from teacher logits (or hard labels fallback)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

SEED = 42
SETUP_DOC = "docs/异机测试环境安装清单.md"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "student.yaml"

sys.path.insert(0, str(ROOT))
from src.metrics import summarize_metrics  # noqa: E402
from src.model_student import build_keras_model, config_from_mapping  # noqa: E402
from src.schema import LABEL_ORDER  # noqa: E402
from src.train_utils import (  # noqa: E402
    load_labeled_records,
    one_hot,
    records_to_xy,
    set_seed,
    softmax_np,
    write_json,
)


def check_tensorflow() -> Optional[str]:
    try:
        import tensorflow  # noqa: F401
    except ImportError:
        return (
            f"TensorFlow is required for distillation. "
            f"Install per {SETUP_DOC} (see requirements-train.txt)."
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Distill Byte TextCNN student model.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Student config YAML.")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    parser.add_argument(
        "--hard-only",
        action="store_true",
        help="Train with hard labels only (skip teacher logits).",
    )
    return parser


def load_teacher_logits(manifest_path: Path) -> Optional[Tuple[Dict[str, np.ndarray], Path]]:
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    logits_path = ROOT / manifest["path"]
    if not logits_path.exists():
        return None
    data = np.load(logits_path, allow_pickle=True)
    ids = [str(x) for x in data["ids"].tolist()]
    logits = data["logits"]
    mapping = {rid: logits[i] for i, rid in enumerate(ids)}
    return mapping, logits_path


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    err = check_tensorflow()
    if err:
        print(err, file=sys.stderr)
        return 2

    import tensorflow as tf

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    set_seed(int(cfg.get("seed", args.seed)))
    student_cfg = config_from_mapping(cfg)
    distill = cfg.get("distillation", {})
    alpha = float(distill.get("alpha", 0.6))
    beta = float(distill.get("beta", 0.4))
    temperature = float(distill.get("temperature", 4.0))
    train_path = ROOT / cfg.get("data", {}).get("train_manifest", "data/processed/train.jsonl")
    val_path = ROOT / cfg.get("data", {}).get("val_manifest", "data/processed/validation.jsonl")
    output_keras = ROOT / cfg.get("output", {}).get(
        "keras_path", "artifacts/student/sms_bytecnn_fp32.keras"
    )
    checkpoint_dir = ROOT / cfg.get("output", {}).get("checkpoint_dir", "artifacts/student")
    logits_manifest = ROOT / distill.get(
        "teacher_manifest", "data/manifests/teacher_logits_manifest.json"
    )

    if not train_path.exists():
        print(f"Train data missing: {train_path}", file=sys.stderr)
        return 1

    train_records = load_labeled_records(train_path)
    val_records = load_labeled_records(val_path) if val_path.exists() else []
    if not train_records:
        print("No labeled training records.", file=sys.stderr)
        return 1

    x_train, y_train = records_to_xy(train_records, max_bytes=student_cfg.max_bytes)
    hard = one_hot(y_train, student_cfg.num_classes)

    # Class weights to reduce collapse toward majority TRANSACTION.
    counts = np.bincount(y_train, minlength=student_cfg.num_classes).astype(np.float32)
    counts = np.maximum(counts, 1.0)
    class_weights = (counts.sum() / (student_cfg.num_classes * counts)).astype(np.float32)
    sample_weights = class_weights[y_train]
    print(f"class_weights={dict(zip(LABEL_ORDER, class_weights.tolist()))}")

    teacher_map = None
    if not args.hard_only:
        loaded = load_teacher_logits(logits_manifest)
        if loaded:
            teacher_map, _ = loaded

    if teacher_map:
        soft_logits = np.stack(
            [
                teacher_map.get(r.id, np.zeros(student_cfg.num_classes, dtype=np.float32))
                for r in train_records
            ]
        )
        soft = softmax_np(soft_logits / temperature)
        use_distill = True
        print(
            f"Distillation: alpha={alpha} beta={beta} T={temperature} "
            f"teacher_logits={len(teacher_map)}"
        )
    else:
        soft = hard
        use_distill = False
        alpha, beta = 1.0, 0.0
        print("Teacher logits missing — training with hard labels only.")

    model = build_keras_model(student_cfg)
    optimizer = tf.keras.optimizers.Adam(
        learning_rate=float(cfg.get("training", {}).get("learning_rate", 1e-3))
    )
    epochs = int(cfg.get("training", {}).get("epochs", 10))
    batch_size = int(cfg.get("training", {}).get("batch_size", 64))

    ce = tf.keras.losses.CategoricalCrossentropy(from_logits=True, reduction="none")
    kl = tf.keras.losses.KLDivergence(reduction="none")

    @tf.function
    def train_step(xb, y_hard, y_soft, sw):
        with tf.GradientTape() as tape:
            logits = model(xb, training=True)
            loss_hard = ce(y_hard, logits)
            student_soft = tf.nn.softmax(logits / temperature)
            loss_soft = kl(y_soft, student_soft) * (temperature * temperature)
            per_example = alpha * loss_hard + beta * loss_soft
            loss = tf.reduce_mean(per_example * sw)
        grads = tape.gradient(loss, model.trainable_variables)
        optimizer.apply_gradients(zip(grads, model.trainable_variables))
        return loss

    n = len(x_train)
    for epoch in range(epochs):
        perm = np.random.permutation(n)
        losses = []
        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            loss = train_step(
                tf.constant(x_train[idx]),
                tf.constant(hard[idx]),
                tf.constant(soft[idx].astype(np.float32)),
                tf.constant(sample_weights[idx]),
            )
            losses.append(float(loss.numpy()))
        print(f"epoch {epoch + 1}/{epochs} loss={np.mean(losses):.4f}")

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    output_keras.parent.mkdir(parents=True, exist_ok=True)
    model.save(output_keras)

    metrics = {}
    if val_records:
        x_val, y_val = records_to_xy(val_records, max_bytes=student_cfg.max_bytes)
        logits = model.predict(x_val, verbose=0)
        preds = np.argmax(logits, axis=-1)
        metrics = summarize_metrics(
            [LABEL_ORDER[i] for i in y_val.tolist()],
            [LABEL_ORDER[i] for i in preds.tolist()],
            LABEL_ORDER,
        )
        write_json(ROOT / "reports" / "metrics" / "student_distill.json", metrics)

        # Collapse gate: refuse to treat all-TRANSACTION (or any single-class) as success.
        unique_preds = set(int(x) for x in preds.tolist())
        if len(unique_preds) == 1 and len(val_records) >= 8:
            write_json(
                checkpoint_dir / "distill_manifest.json",
                {
                    "seed": args.seed,
                    "used_distillation": use_distill,
                    "status": "FAIL_COLLAPSED",
                    "unique_pred_classes": len(unique_preds),
                    "val_metrics": metrics,
                    "keras_path": str(output_keras.relative_to(ROOT)).replace("\\", "/"),
                },
            )
            print(
                "FAIL: student collapsed to a single class on validation. "
                "Do not prune/quantize/export this model.",
                file=sys.stderr,
            )
            return 3
        if float(metrics.get("macro_f1", 0.0)) < 0.25:
            print(
                f"WARNING: macro_f1={metrics['macro_f1']:.3f} is very low; "
                "consider more data / class weights / real distillation.",
                file=sys.stderr,
            )

    write_json(
        checkpoint_dir / "distill_manifest.json",
        {
            "seed": args.seed,
            "used_distillation": use_distill,
            "status": "OK",
            "alpha": alpha,
            "beta": beta,
            "temperature": temperature,
            "keras_path": str(output_keras.relative_to(ROOT)).replace("\\", "/"),
            "train_count": len(train_records),
            "val_metrics": metrics,
        },
    )
    print(f"Wrote student model to {output_keras}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
