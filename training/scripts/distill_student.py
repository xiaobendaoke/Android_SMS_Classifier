#!/usr/bin/env python3
"""Distill Byte TextCNN student from teacher logits (or hard labels fallback)."""
from __future__ import annotations

import argparse
import json
import re
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
    balanced_class_weights,
    filter_records_by_languages,
    load_labeled_records,
    one_hot,
    records_to_xy,
    set_seed,
    softmax_np,
    student_predictions,
    write_json,
)
from scripts.prepare_transaction_specialist_freeze import coverage_subtype  # noqa: E402


def metric_value(metrics: Dict[str, object], label: str, field: str) -> float:
    per_class = metrics.get("per_class", {})
    if not isinstance(per_class, dict):
        return 0.0
    label_metrics = per_class.get(label, {})
    if not isinstance(label_metrics, dict):
        return 0.0
    return float(label_metrics.get(field, 0.0))


def checkpoint_score(metrics: Dict[str, object], targets: Dict[str, float]) -> Tuple[float, ...]:
    """Prefer checkpoints passing every gate; otherwise minimize the worst deficit."""
    macro_f1 = float(metrics.get("macro_f1", 0.0))
    transaction_recall = metric_value(metrics, "TRANSACTION", "recall")
    transaction_precision = metric_value(metrics, "TRANSACTION", "precision")
    harass_f1 = metric_value(metrics, "HARASS", "f1")
    fraud_recall = metric_value(metrics, "FRAUD", "recall")
    gate_ratios = (
        transaction_recall / max(targets["target_transaction_recall"], 1e-9),
        macro_f1 / max(targets["min_macro_f1"], 1e-9),
        transaction_precision / max(targets["min_transaction_precision"], 1e-9),
        harass_f1 / max(targets["min_harass_f1"], 1e-9),
        fraud_recall / max(targets["min_fraud_recall"], 1e-9),
    )
    all_gates_met = float(min(gate_ratios) >= 1.0)
    if all_gates_met:
        return (1.0, transaction_recall, macro_f1, min(gate_ratios), 1.0)
    capped_mean = float(np.mean([min(value, 1.0) for value in gate_ratios]))
    return (0.0, min(gate_ratios), capped_mean, macro_f1, transaction_recall)


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
    primary_focal_gamma = float(distill.get("primary_focal_gamma", 0.0))
    hard_positive_multiplier = float(
        distill.get("transaction_hard_positive_multiplier", 0.0)
    )
    hard_negative_multiplier = float(
        distill.get("transaction_hard_negative_multiplier", 0.0)
    )
    boundary_weight_max = float(distill.get("boundary_weight_max", 3.0))
    teacher_confidence_floor = float(
        distill.get("teacher_confidence_floor", 0.25)
    )
    teacher_confidence_power = float(
        distill.get("teacher_confidence_power", 1.0)
    )
    protection_cfg = cfg.get("transaction_protection", {})
    protection_enabled = bool(
        protection_cfg.get(
            "enabled",
            student_cfg.transaction_protection_head,
        )
    )
    if protection_enabled != student_cfg.transaction_protection_head:
        raise ValueError(
            "model.transaction_protection_head and "
            "transaction_protection.enabled must agree"
        )
    protection_loss_weight = float(protection_cfg.get("loss_weight", 0.35))
    protection_positive_weight = float(protection_cfg.get("positive_weight", 2.0))
    protection_threshold = float(protection_cfg.get("threshold", 0.50))
    protection_focal_gamma = float(protection_cfg.get("focal_gamma", 2.0))
    protection_hard_label_weight = float(
        protection_cfg.get("hard_label_weight", 0.5)
    )
    protection_teacher_temperature = float(
        protection_cfg.get("teacher_temperature", 1.0)
    )
    protection_checkpoint_scope = str(
        protection_cfg.get("checkpoint_scope", "primary")
    )
    if protection_checkpoint_scope not in {"primary", "protected"}:
        raise ValueError(
            "transaction_protection.checkpoint_scope must be primary or protected"
        )
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

    accepted_languages = cfg.get("data", {}).get("accepted_languages", [])
    train_records = filter_records_by_languages(
        load_labeled_records(train_path),
        accepted_languages,
    )
    val_records = (
        filter_records_by_languages(
            load_labeled_records(val_path),
            accepted_languages,
        )
        if val_path.exists()
        else []
    )
    if not train_records:
        print("No labeled training records.", file=sys.stderr)
        return 1

    x_train, y_train = records_to_xy(train_records, max_bytes=student_cfg.max_bytes)
    hard = one_hot(y_train, student_cfg.num_classes)
    transaction_targets = (
        y_train == LABEL_ORDER.index("TRANSACTION")
    ).astype(np.float32)

    # Class weights to reduce collapse toward majority TRANSACTION.
    training_cfg = cfg.get("training", {})
    multipliers_cfg = training_cfg.get("class_weight_multipliers", {})
    weight_strategy = str(training_cfg.get("class_weight_strategy", "balanced"))
    if weight_strategy == "uniform":
        class_weights = np.ones(student_cfg.num_classes, dtype=np.float32)
    elif weight_strategy == "balanced":
        class_weights = balanced_class_weights(
            y_train,
            student_cfg.num_classes,
            multipliers=multipliers_cfg,
        )
        clip_cfg = training_cfg.get("class_weight_clip")
        if clip_cfg is not None:
            if not isinstance(clip_cfg, list) or len(clip_cfg) != 2:
                raise ValueError("training.class_weight_clip must be [minimum, maximum]")
            class_weights = np.clip(
                class_weights,
                float(clip_cfg[0]),
                float(clip_cfg[1]),
            )
            class_weights *= student_cfg.num_classes / float(class_weights.sum())
    else:
        raise ValueError(
            "training.class_weight_strategy must be 'balanced' or 'uniform'"
        )
    sample_weights = class_weights[y_train]
    carrier_repayment_weight = float(
        training_cfg.get("carrier_repayment_positive_multiplier", 1.0)
    )
    carrier_repayment_boundary_weight = float(
        training_cfg.get("carrier_repayment_boundary_multiplier", 1.0)
    )
    if carrier_repayment_weight < 1.0:
        raise ValueError(
            "training.carrier_repayment_positive_multiplier must be >= 1.0"
        )
    if carrier_repayment_boundary_weight < 1.0:
        raise ValueError(
            "training.carrier_repayment_boundary_multiplier must be >= 1.0"
        )
    hard_boundary_multiplier = float(
        training_cfg.get("hard_boundary_multiplier", 1.0)
    )
    if hard_boundary_multiplier < 1.0:
        raise ValueError(
            "training.hard_boundary_multiplier must be >= 1.0"
        )
    hard_boundary_labels = [
        str(label)
        for label in training_cfg.get(
            "hard_boundary_labels", ["AD", "FRAUD", "HARASS"]
        )
    ]
    if not hard_boundary_labels:
        raise ValueError("training.hard_boundary_labels must not be empty")
    carrier_repayment_pattern = re.compile(
        r"(?:中国移动|中国联通|中国电信|10086|10010|10000).{0,48}"
        r"(?:话费|流量|套餐|停机|余额|账单|充值|扣费)"
        r"|(?:还款|账单).{0,24}(?:成功|已入账|已还清|到期|应还|最低还款)"
    )
    carrier_repayment_boundary = np.asarray(
        [
            bool(carrier_repayment_pattern.search(record.text))
            for record in train_records
        ],
        dtype=bool,
    )
    carrier_repayment_positive = np.asarray(
        [
            bool(transaction_targets[index] > 0.5)
            and bool(carrier_repayment_boundary[index])
            for index, record in enumerate(train_records)
        ],
        dtype=bool,
    )
    if carrier_repayment_boundary_weight > 1.0:
        sample_weights = sample_weights * np.where(
            carrier_repayment_boundary,
            carrier_repayment_boundary_weight,
            1.0,
        ).astype(np.float32)
    if carrier_repayment_weight > 1.0:
        sample_weights = sample_weights * np.where(
            carrier_repayment_positive,
            carrier_repayment_weight,
            1.0,
        ).astype(np.float32)
    hard_boundary = np.asarray(
        [
            coverage_subtype(record.text) is not None
            and LABEL_ORDER[int(y_train[index])] in hard_boundary_labels
            for index, record in enumerate(train_records)
        ],
        dtype=bool,
    )
    hard_boundary_label_counts: Dict[str, int] = {}
    for index in np.flatnonzero(hard_boundary):
        label = LABEL_ORDER[int(y_train[index])]
        hard_boundary_label_counts[label] = (
            hard_boundary_label_counts.get(label, 0) + 1
        )
    if hard_boundary_multiplier > 1.0:
        sample_weights = sample_weights * np.where(
            hard_boundary,
            hard_boundary_multiplier,
            1.0,
        ).astype(np.float32)
    print(
        f"class_weight_strategy={weight_strategy} "
        f"class_weights={dict(zip(LABEL_ORDER, class_weights.tolist()))} "
        f"carrier_repayment_boundary_count="
        f"{int(carrier_repayment_boundary.sum())} "
        f"carrier_repayment_boundary_multiplier={carrier_repayment_boundary_weight} "
        f"carrier_repayment_positive_count="
        f"{int(carrier_repayment_positive.sum())} "
        f"carrier_repayment_positive_multiplier={carrier_repayment_weight}"
    )
    print(
        f"hard_boundary_multiplier={hard_boundary_multiplier} "
        f"hard_boundary_labels={hard_boundary_labels} "
        f"hard_boundary_count={int(hard_boundary.sum())} "
        f"hard_boundary_label_counts={hard_boundary_label_counts}"
    )

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
        teacher_probabilities = softmax_np(soft_logits)
        teacher_transaction_probability = softmax_np(
            soft_logits / protection_teacher_temperature
        )[:, LABEL_ORDER.index("TRANSACTION")]
        teacher_true_probability = teacher_probabilities[
            np.arange(len(y_train)), y_train
        ]
        distill_sample_weights = np.power(
            np.maximum(teacher_true_probability, teacher_confidence_floor),
            teacher_confidence_power,
        ).astype(np.float32)
        boundary_sample_weights = np.where(
            transaction_targets > 0.5,
            1.0
            + hard_positive_multiplier
            * (1.0 - teacher_transaction_probability),
            1.0
            + hard_negative_multiplier
            * teacher_transaction_probability,
        )
        boundary_sample_weights = np.clip(
            boundary_sample_weights,
            1.0,
            boundary_weight_max,
        ).astype(np.float32)
        boundary_sample_weights /= float(boundary_sample_weights.mean())
        transaction_training_targets = (
            protection_hard_label_weight * transaction_targets
            + (1.0 - protection_hard_label_weight)
            * teacher_transaction_probability
        ).astype(np.float32)
        use_distill = True
        print(
            f"Distillation: alpha={alpha} beta={beta} T={temperature} "
            f"teacher_logits={len(teacher_map)}"
        )
    else:
        soft = hard
        transaction_training_targets = transaction_targets
        distill_sample_weights = np.ones(len(y_train), dtype=np.float32)
        boundary_sample_weights = np.ones(len(y_train), dtype=np.float32)
        use_distill = False
        alpha, beta = 1.0, 0.0
        print("Teacher logits missing — training with hard labels only.")

    model = build_keras_model(student_cfg)
    optimizer = tf.keras.optimizers.Adam(
        learning_rate=float(cfg.get("training", {}).get("learning_rate", 1e-3))
    )
    gradient_clip_norm = training_cfg.get("gradient_clip_norm")
    if gradient_clip_norm is not None:
        gradient_clip_norm = float(gradient_clip_norm)
        if gradient_clip_norm <= 0.0:
            raise ValueError("training.gradient_clip_norm must be positive when set")
    epochs = int(training_cfg.get("epochs", 10))
    batch_size = int(training_cfg.get("batch_size", 64))
    patience = int(training_cfg.get("early_stopping_patience", 4))
    min_epochs = int(training_cfg.get("min_epochs", 5))
    targets = {
        "target_transaction_recall": float(
            training_cfg.get("target_transaction_recall", 0.985)
        ),
        "min_transaction_precision": float(
            training_cfg.get("min_transaction_precision", 0.92)
        ),
        "min_macro_f1": float(training_cfg.get("min_macro_f1", 0.86)),
        "min_harass_f1": float(training_cfg.get("min_harass_f1", 0.80)),
        "min_fraud_recall": float(training_cfg.get("min_fraud_recall", 0.80)),
    }
    enforce_model_targets = bool(
        training_cfg.get("enforce_model_validation_targets", True)
    )

    ce = tf.keras.losses.CategoricalCrossentropy(from_logits=True, reduction="none")
    kl = tf.keras.losses.KLDivergence(reduction="none")

    @tf.function
    def train_step(
        xb,
        y_hard,
        y_soft,
        y_transaction,
        sw,
        boundary_weight,
        distill_weight,
    ):
        with tf.GradientTape() as tape:
            all_logits = model(xb, training=True)
            logits = all_logits[:, : student_cfg.num_classes]
            loss_hard = ce(y_hard, logits)
            hard_true_probability = tf.reduce_sum(
                y_hard * tf.nn.softmax(logits),
                axis=-1,
            )
            hard_focal_weight = tf.pow(
                1.0 - hard_true_probability,
                primary_focal_gamma,
            )
            student_soft = tf.nn.softmax(logits / temperature)
            loss_soft = kl(y_soft, student_soft) * (temperature * temperature)
            # Class weighting belongs only on the supervised CE term. Weighting
            # KL by hard labels distorts the teacher distribution.
            per_example = (
                alpha
                * loss_hard
                * sw
                * boundary_weight
                * hard_focal_weight
                + beta * loss_soft * distill_weight
            )
            if protection_enabled:
                protection_logits = all_logits[:, student_cfg.num_classes]
                protection_bce = tf.nn.sigmoid_cross_entropy_with_logits(
                    labels=y_transaction,
                    logits=protection_logits,
                )
                protection_prob = tf.nn.sigmoid(protection_logits)
                protection_pt = (
                    y_transaction * protection_prob
                    + (1.0 - y_transaction) * (1.0 - protection_prob)
                )
                protection_class_weight = (
                    y_transaction * protection_positive_weight
                    + (1.0 - y_transaction)
                )
                protection_loss = (
                    protection_class_weight
                    * tf.pow(1.0 - protection_pt, protection_focal_gamma)
                    * protection_bce
                )
                per_example += (
                    protection_loss_weight
                    * protection_loss
                    * boundary_weight
                )
            loss = tf.reduce_mean(per_example)
        grads = tape.gradient(loss, model.trainable_variables)
        if gradient_clip_norm is not None:
            grads, _ = tf.clip_by_global_norm(grads, gradient_clip_norm)
        optimizer.apply_gradients(zip(grads, model.trainable_variables))
        return loss

    x_val = y_val = None
    if val_records:
        x_val, y_val = records_to_xy(val_records, max_bytes=student_cfg.max_bytes)

    n = len(x_train)
    best_weights = None
    best_metrics: Dict[str, object] = {}
    best_score: Optional[Tuple[float, ...]] = None
    best_epoch = 0
    stale_epochs = 0
    for epoch in range(epochs):
        perm = np.random.permutation(n)
        losses = []
        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            loss = train_step(
                tf.constant(x_train[idx]),
                tf.constant(hard[idx]),
                tf.constant(soft[idx].astype(np.float32)),
                tf.constant(transaction_training_targets[idx]),
                tf.constant(sample_weights[idx]),
                tf.constant(boundary_sample_weights[idx]),
                tf.constant(distill_sample_weights[idx]),
            )
            losses.append(float(loss.numpy()))
        line = f"epoch {epoch + 1}/{epochs} loss={np.mean(losses):.4f}"
        if x_val is not None and y_val is not None:
            val_logits = model.predict(x_val, verbose=0)
            primary_val_preds = student_predictions(
                val_logits,
                num_classes=student_cfg.num_classes,
            )
            protected_val_preds = student_predictions(
                val_logits,
                num_classes=student_cfg.num_classes,
                transaction_threshold=(
                    protection_threshold if protection_enabled else None
                ),
            )
            val_preds = (
                protected_val_preds
                if protection_checkpoint_scope == "protected"
                else primary_val_preds
            )
            epoch_metrics = summarize_metrics(
                [LABEL_ORDER[i] for i in y_val.tolist()],
                [LABEL_ORDER[i] for i in val_preds.tolist()],
                LABEL_ORDER,
            )
            score = checkpoint_score(epoch_metrics, targets)
            unique_classes = len(set(int(x) for x in val_preds.tolist()))
            if unique_classes >= 3 and (best_score is None or score > best_score):
                best_score = score
                best_weights = model.get_weights()
                best_metrics = epoch_metrics
                best_epoch = epoch + 1
                stale_epochs = 0
            else:
                stale_epochs += 1
            line += (
                f" val_macro_f1={float(epoch_metrics['macro_f1']):.4f}"
                f" val_txn_recall={metric_value(epoch_metrics, 'TRANSACTION', 'recall'):.4f}"
                f" val_fraud_recall={metric_value(epoch_metrics, 'FRAUD', 'recall'):.4f}"
            )
        print(line)
        if epoch + 1 >= min_epochs and stale_epochs >= patience:
            print(f"early stopping: no checkpoint improvement for {patience} epochs")
            break

    if best_weights is not None:
        model.set_weights(best_weights)
        print(f"restored best validation checkpoint from epoch {best_epoch}")

    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    output_keras.parent.mkdir(parents=True, exist_ok=True)
    model.save(output_keras)

    metrics = {}
    if val_records:
        assert x_val is not None and y_val is not None
        logits = model.predict(x_val, verbose=0)
        primary_preds = student_predictions(
            logits,
            num_classes=student_cfg.num_classes,
        )
        preds = student_predictions(
            logits,
            num_classes=student_cfg.num_classes,
            transaction_threshold=(
                protection_threshold if protection_enabled else None
            ),
        )
        metrics = summarize_metrics(
            [LABEL_ORDER[i] for i in y_val.tolist()],
            [LABEL_ORDER[i] for i in preds.tolist()],
            LABEL_ORDER,
        )
        primary_metrics = summarize_metrics(
            [LABEL_ORDER[i] for i in y_val.tolist()],
            [LABEL_ORDER[i] for i in primary_preds.tolist()],
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
                    "primary_val_metrics": primary_metrics,
                    "best_epoch": best_epoch,
                    "targets": targets,
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

    gate_errors = []
    if val_records:
        checks = (
            (
                "transaction_recall",
                metric_value(metrics, "TRANSACTION", "recall"),
                targets["target_transaction_recall"],
            ),
            (
                "transaction_precision",
                metric_value(metrics, "TRANSACTION", "precision"),
                targets["min_transaction_precision"],
            ),
            ("macro_f1", float(metrics.get("macro_f1", 0.0)), targets["min_macro_f1"]),
            (
                "harass_f1",
                metric_value(metrics, "HARASS", "f1"),
                targets["min_harass_f1"],
            ),
            (
                "fraud_recall",
                metric_value(metrics, "FRAUD", "recall"),
                targets["min_fraud_recall"],
            ),
        )
        gate_errors = [
            f"{name}={value:.6f} < {target:.6f}"
            for name, value, target in checks
            if value < target
        ]

    status = (
        "OK"
        if not gate_errors
        else (
            "FAIL_VALIDATION_TARGETS"
            if enforce_model_targets
            else "PENDING_PIPELINE_VALIDATION"
        )
    )
    write_json(
        checkpoint_dir / "distill_manifest.json",
        {
            "seed": args.seed,
            "used_distillation": use_distill,
            "status": status,
            "alpha": alpha,
            "beta": beta,
            "temperature": temperature,
            "primary_focal_gamma": primary_focal_gamma,
            "boundary_hard_positive_multiplier": hard_positive_multiplier,
            "boundary_hard_negative_multiplier": hard_negative_multiplier,
            "boundary_weight_max": boundary_weight_max,
            "teacher_confidence_floor": teacher_confidence_floor,
            "teacher_confidence_power": teacher_confidence_power,
            "boundary_weight_summary": {
                "min": float(boundary_sample_weights.min()),
                "mean": float(boundary_sample_weights.mean()),
                "max": float(boundary_sample_weights.max()),
            },
            "distill_weight_summary": {
                "min": float(distill_sample_weights.min()),
                "mean": float(distill_sample_weights.mean()),
                "max": float(distill_sample_weights.max()),
            },
            "keras_path": str(output_keras.relative_to(ROOT)).replace("\\", "/"),
            "train_count": len(train_records),
            "val_metrics": metrics,
            "primary_val_metrics": primary_metrics if val_records else {},
            "best_epoch": best_epoch,
            "targets": targets,
            "gate_errors": gate_errors,
            "enforce_model_validation_targets": enforce_model_targets,
            "class_weights": dict(zip(LABEL_ORDER, class_weights.tolist())),
            "carrier_repayment_boundary_count": int(
                carrier_repayment_boundary.sum()
            ),
            "carrier_repayment_boundary_multiplier": carrier_repayment_boundary_weight,
            "carrier_repayment_positive_count": int(
                carrier_repayment_positive.sum()
            ),
            "carrier_repayment_positive_multiplier": carrier_repayment_weight,
            "hard_boundary_multiplier": hard_boundary_multiplier,
            "hard_boundary_labels": hard_boundary_labels,
            "hard_boundary_count": int(hard_boundary.sum()),
            "hard_boundary_label_counts": hard_boundary_label_counts,
            "transaction_protection": {
                "enabled": protection_enabled,
                "output_index": (
                    student_cfg.num_classes if protection_enabled else None
                ),
                "threshold": protection_threshold,
                "loss_weight": protection_loss_weight,
                "positive_weight": protection_positive_weight,
                "focal_gamma": protection_focal_gamma,
                "hard_label_weight": protection_hard_label_weight,
                "teacher_temperature": protection_teacher_temperature,
                "checkpoint_scope": protection_checkpoint_scope,
            },
        },
    )
    print(f"Wrote student model to {output_keras}")
    if gate_errors and enforce_model_targets:
        print(
            "FAIL: validation targets not met; do not evaluate the locked test set:\n  - "
            + "\n  - ".join(gate_errors),
            file=sys.stderr,
        )
        return 4
    if gate_errors:
        print(
            "Model-only validation targets are not all met; continuing because "
            "the release gate is configured for the transaction-protected pipeline."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
