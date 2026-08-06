#!/usr/bin/env python3
"""Structured channel pruning for Byte TextCNN (physically shrinks Conv1D filters)."""
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
DEFAULT_CONFIG = ROOT / "configs" / "pruning.yaml"
STUDENT_CONFIG = ROOT / "configs" / "student.yaml"

sys.path.insert(0, str(ROOT))
from src.metrics import summarize_metrics  # noqa: E402
from src.model_student import StudentModelConfig, build_keras_model, config_from_mapping  # noqa: E402
from src.schema import LABEL_ORDER  # noqa: E402
from src.train_utils import (  # noqa: E402
    load_labeled_records,
    records_to_xy,
    set_seed,
    student_predictions,
    write_json,
)


def check_tensorflow() -> Optional[str]:
    try:
        import tensorflow  # noqa: F401
    except ImportError:
        return (
            f"TensorFlow is required for structured pruning. "
            f"Install per {SETUP_DOC} (see requirements-train.txt)."
        )
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Structured Conv1D channel pruning.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Pruning config YAML.")
    parser.add_argument(
        "--student-config",
        type=Path,
        default=STUDENT_CONFIG,
        help="Student config YAML used for architecture and data manifests.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Write pruning plan without applying.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports" / "metrics" / "prune_plan.json",
        help="Pruning plan/report path.",
    )
    parser.add_argument(
        "--allow-dense-fallback",
        action="store_true",
        help=(
            "If all prune ratios exceed accuracy budget, copy the dense FP32 model "
            "to the pruned output path and exit 0 (for Colab/synthetic smoke)."
        ),
    )
    parser.add_argument(
        "--max-macro-f1-drop",
        type=float,
        default=None,
        help="Override config max_macro_f1_drop (e.g. 0.15 on tiny val sets).",
    )
    parser.add_argument(
        "--max-txn-recall-drop",
        type=float,
        default=None,
        help="Override config max_transaction_recall_drop.",
    )
    return parser


def l1_channel_scores(kernel: np.ndarray) -> np.ndarray:
    return np.sum(np.abs(kernel), axis=(0, 1))


def select_keep_indices(scores: np.ndarray, keep: int) -> np.ndarray:
    order = np.argsort(-scores)
    return np.sort(order[:keep])


def eval_model(model, val_path: Path, max_bytes: int) -> Dict:
    if not val_path.exists():
        return {}
    val_records = load_labeled_records(val_path)
    if not val_records:
        return {}
    xv, yv = records_to_xy(val_records, max_bytes=max_bytes)
    logits = model.predict(xv, verbose=0)
    preds = student_predictions(
        logits,
        transaction_threshold=(
            0.5 if logits.shape[-1] > len(LABEL_ORDER) else None
        ),
    )
    return summarize_metrics(
        [LABEL_ORDER[i] for i in yv.tolist()],
        [LABEL_ORDER[i] for i in preds.tolist()],
        LABEL_ORDER,
    )


def within_budget(
    baseline: Dict,
    candidate: Dict,
    max_txn_drop: float,
    max_f1_drop: float,
) -> bool:
    if not baseline or not candidate:
        return True
    base_txn = float(baseline.get("per_class", {}).get("TRANSACTION", {}).get("recall", 0.0))
    cand_txn = float(candidate.get("per_class", {}).get("TRANSACTION", {}).get("recall", 0.0))
    base_f1 = float(baseline.get("macro_f1", 0.0))
    cand_f1 = float(candidate.get("macro_f1", 0.0))
    return (base_txn - cand_txn) <= max_txn_drop and (base_f1 - cand_f1) <= max_f1_drop


def prune_once(
    src,
    base_cfg: StudentModelConfig,
    ratio: float,
    train_path: Path,
    epochs: int,
    lr: float,
):
    import tensorflow as tf

    kept_filters = max(8, int(round(base_cfg.conv_filters * (1.0 - ratio))))
    pruned_cfg = StudentModelConfig(
        vocab_size=base_cfg.vocab_size,
        embedding_dim=base_cfg.embedding_dim,
        conv_filters=kept_filters,
        conv_kernels=list(base_cfg.conv_kernels),
        dense_units=base_cfg.dense_units,
        dropout=base_cfg.dropout,
        num_classes=base_cfg.num_classes,
        transaction_protection_head=base_cfg.transaction_protection_head,
        transaction_hidden_units=base_cfg.transaction_hidden_units,
        max_bytes=base_cfg.max_bytes,
        pad_id=base_cfg.pad_id,
        byte_offset=base_cfg.byte_offset,
    )
    dst = build_keras_model(pruned_cfg)
    dst.get_layer("byte_embedding").set_weights(src.get_layer("byte_embedding").get_weights())
    for idx, kernel_size in enumerate(base_cfg.conv_kernels):
        src_name = f"conv1d_k{kernel_size}_{idx}"
        kernel, bias = src.get_layer(src_name).get_weights()
        scores = l1_channel_scores(kernel)
        keep_idx = select_keep_indices(scores, kept_filters)
        dst.get_layer(src_name).set_weights([kernel[:, :, keep_idx], bias[keep_idx]])

    if train_path.exists():
        records = load_labeled_records(train_path)
        x, y = records_to_xy(records, max_bytes=pruned_cfg.max_bytes)
        def dual_head_loss(y_true, y_pred):
            labels = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
            class_loss = tf.keras.losses.sparse_categorical_crossentropy(
                labels,
                y_pred[:, : len(LABEL_ORDER)],
                from_logits=True,
            )
            transaction_targets = tf.cast(
                tf.equal(labels, LABEL_ORDER.index("TRANSACTION")),
                tf.float32,
            )
            protection_loss = tf.nn.weighted_cross_entropy_with_logits(
                labels=transaction_targets,
                logits=y_pred[:, len(LABEL_ORDER)],
                pos_weight=1.5,
            )
            return class_loss + 0.35 * protection_loss

        dst.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
            loss=(
                dual_head_loss
                if pruned_cfg.transaction_protection_head
                else tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
            ),
            metrics=["accuracy"],
        )
        dst.fit(x, y, epochs=epochs, batch_size=64, verbose=1)
    return dst, pruned_cfg, kept_filters


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    ratios = [float(x) for x in cfg.get("prune_ratios", [0.25, 0.15, 0.10])]
    input_model = ROOT / cfg.get("input_model", "artifacts/student/sms_bytecnn_fp32.keras")
    output_model = ROOT / cfg.get("output_model", "artifacts/student/sms_bytecnn_pruned.keras")
    constraints = cfg.get("constraints", {})
    max_txn_drop = float(
        args.max_txn_recall_drop
        if args.max_txn_recall_drop is not None
        else constraints.get("max_transaction_recall_drop", 0.005)
    )
    max_f1_drop = float(
        args.max_macro_f1_drop
        if args.max_macro_f1_drop is not None
        else constraints.get("max_macro_f1_drop", 0.01)
    )

    plan = {
        "seed": args.seed,
        "importance": cfg.get("importance", "l1_norm"),
        "prune_ratios_tried": ratios,
        "input_model": str(input_model.relative_to(ROOT)).replace("\\", "/")
        if input_model.exists()
        else str(input_model),
        "output_model": str(output_model.relative_to(ROOT)).replace("\\", "/"),
        "constraints": constraints,
        "method": "rebuild_smaller_conv_channels",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    if args.plan_only:
        print(f"Pruning plan: {args.report}")
        return 0

    err = check_tensorflow()
    if err:
        print(err, file=sys.stderr)
        print(f"Pruning plan written: {args.report}")
        return 2

    import tensorflow as tf

    if not input_model.exists():
        print(f"Input Keras model missing: {input_model}", file=sys.stderr)
        return 1

    set_seed(int(cfg.get("seed", args.seed)))
    with args.student_config.open(encoding="utf-8") as fh:
        student_yaml = yaml.safe_load(fh) or {}
    base_cfg = config_from_mapping(student_yaml)
    src = tf.keras.models.load_model(input_model)

    train_path = ROOT / student_yaml.get("data", {}).get("train_manifest", "data/processed/train.jsonl")
    val_path = ROOT / student_yaml.get("data", {}).get("val_manifest", "data/processed/validation.jsonl")
    finetune = cfg.get("finetune", {})
    epochs = int(finetune.get("epochs", 3))
    lr = float(finetune.get("learning_rate", 5e-4))

    baseline = eval_model(src, val_path, base_cfg.max_bytes)
    plan["baseline_val_metrics"] = baseline

    chosen = None
    for ratio in ratios:
        print(f"Trying prune_ratio={ratio}")
        dst, pruned_cfg, kept = prune_once(src, base_cfg, ratio, train_path, epochs, lr)
        metrics = eval_model(dst, val_path, pruned_cfg.max_bytes)
        attempt = {
            "prune_ratio": ratio,
            "kept_filters": kept,
            "val_metrics": metrics,
            "within_budget": within_budget(baseline, metrics, max_txn_drop, max_f1_drop),
        }
        plan.setdefault("attempts", []).append(attempt)
        if attempt["within_budget"]:
            chosen = (dst, pruned_cfg, kept, ratio, metrics)
            break
        print(f"Ratio {ratio} exceeded budget; trying next.")

    if chosen is None:
        # Keep densest (lowest ratio last tried) but mark FAIL — do not silently accept.
        plan["status"] = "FAIL_BUDGET"
        plan["effective_constraints"] = {
            "max_transaction_recall_drop": max_txn_drop,
            "max_macro_f1_drop": max_f1_drop,
        }
        write_json(args.report, plan)
        write_json(ROOT / "reports" / "metrics" / "prune.json", plan)
        if args.allow_dense_fallback and input_model.exists():
            import shutil

            output_model.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_model, output_model)
            plan["status"] = "DENSE_FALLBACK"
            plan["note"] = (
                "All prune ratios exceeded budget on current val set; "
                "copied dense FP32 model to pruned path so quantize can continue. "
                "Not a production prune accept."
            )
            write_json(args.report, plan)
            write_json(ROOT / "reports" / "metrics" / "prune.json", plan)
            print(
                "WARN: prune budget failed; dense fallback written to "
                f"{output_model} (status=DENSE_FALLBACK)",
                file=sys.stderr,
            )
            return 0
        print(
            "FAIL: all prune ratios exceeded accuracy budget. "
            "Keeping dense model; do not export pruned artifact. "
            "Retry with --allow-dense-fallback for smoke pipelines.",
            file=sys.stderr,
        )
        return 3

    dst, pruned_cfg, kept, ratio, metrics = chosen
    output_model.parent.mkdir(parents=True, exist_ok=True)
    dst.save(output_model)
    plan.update(
        {
            "status": "APPLIED",
            "prune_ratio": ratio,
            "kept_filters": kept,
            "original_filters": base_cfg.conv_filters,
            "val_metrics": metrics,
        }
    )
    write_json(args.report, plan)
    write_json(ROOT / "reports" / "metrics" / "prune.json", metrics or plan)
    print(f"Wrote pruned model to {output_model} (ratio={ratio})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
