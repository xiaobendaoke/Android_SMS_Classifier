#!/usr/bin/env python3
"""Evaluate classifier on frozen test set.

Modes:
  tflite   — TFLite student model (default when model exists)
  rule     — rule heuristics only (explicit; must not be mistaken for model metrics)
  predictions — external predictions JSONL
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import yaml

SEED = 42

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
from src.byte_encoder import encode_text  # noqa: E402
from src.metrics import summarize_metrics, wilson_interval  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import LABEL_ORDER, load_jsonl  # noqa: E402
from src.train_utils import set_seed, split_student_logits  # noqa: E402
from src.transaction_protection import (  # noqa: E402
    apply_transaction_protection_batch,
    load_protection_rules,
)

RULE_PATTERNS: List[Tuple[str, str, int]] = [
    ("TRANSACTION", r"(?:入账|扣款|payment|pembayaran|भुगतान|订单|flight|shipped|ticket|deposit)", 80),
    ("AD", r"(?:优惠|promo|diskon|click|prize|sale|इनाम|gratis|offer|discount|抽奖)", 70),
    ("HARASS", r"(?:还钱|pay me|utang|परेशान|abai|contact|harass|terus hubungi)", 75),
    ("FRAUD", r"(?:异常|verify|http|blocked|diblokir|ब्लॉक|phish|OTP|冻结|locked|refund pending)", 90),
]

DEFAULT_TFLITE = ROOT / "artifacts" / "student" / "sms_bytecnn_int8.tflite"
SDK_TFLITE = (
    ROOT.parent
    / "android"
    / "classifier-sdk"
    / "src"
    / "main"
    / "assets"
    / "model"
    / "sms_bytecnn_int8.tflite"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate model on frozen test set.")
    parser.add_argument(
        "--test",
        type=Path,
        default=ROOT / "data" / "processed" / "test.jsonl",
        help="Frozen test JSONL.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "keras", "tflite", "pipeline", "rule", "predictions"],
        default="auto",
        help="Evaluation path. auto prefers TFLite when present.",
    )
    parser.add_argument(
        "--keras",
        type=Path,
        default=None,
        help="Keras student path for --mode keras/pipeline.",
    )
    parser.add_argument(
        "--tflite",
        type=Path,
        default=None,
        help="TFLite model path (defaults to artifacts or SDK assets).",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="Optional JSONL with id + predicted_label fields.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "evaluate.json",
        help="Metrics output JSON.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    parser.add_argument("--stage", type=str, default="evaluation")
    parser.add_argument(
        "--rules-dir",
        type=Path,
        default=ROOT / "rules" / "rules",
        help="Exported JSON rules used by --mode pipeline.",
    )
    parser.add_argument("--error-samples", type=int, default=0)
    parser.add_argument("--error-output", type=Path, default=None)
    parser.add_argument(
        "--require-acceptance",
        action="store_true",
        help="Fail unless configured validation targets all pass.",
    )
    parser.add_argument(
        "--targets-config",
        type=Path,
        default=ROOT / "configs" / "student.yaml",
    )
    return parser


def rule_predict(text: str) -> str:
    norm = normalize_text(text)
    best_label = LABEL_ORDER[0]
    best_score = -1
    for label, pattern, priority in RULE_PATTERNS:
        if re.search(pattern, norm, flags=re.IGNORECASE):
            if priority > best_score:
                best_score = priority
                best_label = label
    return best_label


def load_predictions(path: Path) -> Dict[str, str]:
    preds: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        preds[str(row["id"])] = str(row.get("predicted_label", row.get("label", "")))
    return preds


def resolve_tflite(path: Optional[Path]) -> Optional[Path]:
    if path and path.exists():
        return path
    for candidate in (DEFAULT_TFLITE, SDK_TFLITE):
        if candidate.exists():
            return candidate
    return None


def _decode_student_outputs(outputs) -> Tuple[List[str], List[bool]]:
    import numpy as np

    class_logits, protection_logits = split_student_logits(
        np.asarray(outputs),
        len(LABEL_ORDER),
    )
    indices = np.argmax(class_logits, axis=-1)
    labels = [LABEL_ORDER[int(index)] for index in indices]
    if protection_logits is None:
        return labels, [False] * len(labels)
    protection_probs = 1.0 / (1.0 + np.exp(-protection_logits))
    return labels, [bool(value >= 0.5) for value in protection_probs]


def keras_predict_batch(
    model_path: Path,
    texts: Sequence[str],
) -> Tuple[List[str], List[bool]]:
    import numpy as np
    import tensorflow as tf

    model = tf.keras.models.load_model(model_path)
    max_bytes = int(model.input_shape[-1])
    encoded = np.asarray(
        [
            encode_text(normalize_text(text), length=max_bytes)
            for text in texts
        ],
        dtype=np.int32,
    )
    return _decode_student_outputs(model.predict(encoded, verbose=0))


def tflite_predict_batch(
    model_path: Path,
    texts: Sequence[str],
) -> Tuple[List[str], List[bool]]:
    import numpy as np
    import tensorflow as tf

    interpreter = tf.lite.Interpreter(model_content=model_path.read_bytes())
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]
    outputs = []
    for text in texts:
        ids = encode_text(normalize_text(text), length=512)
        inp = np.asarray([ids], dtype=input_details["dtype"])
        interpreter.set_tensor(input_details["index"], inp)
        interpreter.invoke()
        out = interpreter.get_tensor(output_details["index"])[0]
        if out.dtype != np.float32 and out.dtype != np.float64:
            scale, zero_point = output_details.get("quantization", (0.0, 0))
            if scale:
                out = (
                    out.astype(np.float32) - float(zero_point)
                ) * float(scale)
        outputs.append(out)
    return _decode_student_outputs(np.asarray(outputs))


def per_language_metrics(records, y_true, y_pred) -> Dict[str, object]:
    by_lang: Dict[str, List[int]] = defaultdict(list)
    for i, record in enumerate(records):
        by_lang[record.language or "unknown"].append(i)
    out: Dict[str, object] = {}
    for lang, idxs in sorted(by_lang.items()):
        yt = [y_true[i] for i in idxs]
        yp = [y_pred[i] for i in idxs]
        out[lang] = summarize_metrics(yt, yp, LABEL_ORDER)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    set_seed(args.seed)
    if not args.test.exists():
        print(f"Test set missing: {args.test}", file=sys.stderr)
        return 1

    records = load_jsonl(args.test)
    evaluable = [r for r in records if r.label in LABEL_ORDER]
    needs_review = [r for r in records if r.label == "NEEDS_REVIEW"]

    mode = args.mode
    if mode == "auto":
        if args.predictions and args.predictions.exists():
            mode = "predictions"
        elif args.keras and args.keras.exists():
            mode = "keras"
        elif resolve_tflite(args.tflite) is not None:
            mode = "tflite"
        else:
            print(
                "No TFLite model found. Refusing to silently use rule heuristics as "
                "model metrics. Pass --mode rule explicitly if that is intended.",
                file=sys.stderr,
            )
            return 1

    raw_predictions: Optional[List[str]] = None
    model_protection_flags: List[bool] = [False] * len(evaluable)
    protection_decisions = []
    if mode == "predictions":
        if not args.predictions or not args.predictions.exists():
            print("--mode predictions requires --predictions file", file=sys.stderr)
            return 1
        pred_map = load_predictions(args.predictions)
        y_pred = [pred_map.get(r.id, "AD") for r in evaluable]
        classifier = "predictions_file"
        model_path_str = None
    elif mode == "rule":
        y_pred = [rule_predict(r.text) for r in evaluable]
        classifier = "rule_heuristics"
        model_path_str = None
        print(
            "WARNING: rule_heuristics metrics must not be reported as model/SDK "
            "transaction recall.",
            file=sys.stderr,
        )
    elif mode == "keras":
        if not args.keras or not args.keras.exists():
            print("--mode keras requires an existing --keras model", file=sys.stderr)
            return 1
        try:
            y_pred, model_protection_flags = keras_predict_batch(
                args.keras,
                [record.text for record in evaluable],
            )
        except ImportError:
            print("TensorFlow required for --mode keras.", file=sys.stderr)
            return 2
        classifier = "keras"
        model_path_str = str(args.keras).replace("\\", "/")
    elif mode in {"tflite", "pipeline"}:
        model_path = resolve_tflite(args.tflite)
        use_keras_pipeline = (
            mode == "pipeline"
            and args.keras is not None
            and args.keras.exists()
        )
        if model_path is None and not use_keras_pipeline:
            print("TFLite model not found.", file=sys.stderr)
            return 1
        try:
            if use_keras_pipeline:
                raw_predictions, model_protection_flags = keras_predict_batch(
                    args.keras,
                    [record.text for record in evaluable],
                )
            else:
                assert model_path is not None
                raw_predictions, model_protection_flags = tflite_predict_batch(
                    model_path,
                    [record.text for record in evaluable],
                )
        except ImportError:
            print(
                "TensorFlow required for --mode tflite. "
                "Install per docs/异机测试环境安装清单.md",
                file=sys.stderr,
            )
            return 2
        if mode == "pipeline":
            rules = load_protection_rules(args.rules_dir)
            protection_decisions = apply_transaction_protection_batch(
                [record.text for record in evaluable],
                raw_predictions,
                rules,
                model_transaction_protect=model_protection_flags,
            )
            y_pred = [decision.predicted_label for decision in protection_decisions]
            classifier = (
                "keras_transaction_protection_pipeline"
                if use_keras_pipeline
                else "tflite_transaction_protection_pipeline"
            )
        else:
            y_pred = raw_predictions
            classifier = "tflite"
        try:
            selected_model = args.keras if use_keras_pipeline else model_path
            assert selected_model is not None
            model_path_str = str(
                selected_model.relative_to(ROOT.parent)
            ).replace("\\", "/")
        except ValueError:
            model_path_str = str(selected_model).replace("\\", "/")
    else:
        print(f"Unsupported evaluation mode: {mode}", file=sys.stderr)
        return 1

    y_true = [r.label for r in evaluable]
    summary = summarize_metrics(y_true, y_pred, LABEL_ORDER)
    acceptance_summary = summary
    acceptance_languages: List[str] = []
    acceptance_indices = list(range(len(evaluable)))
    pred_dist = dict(Counter(y_pred))
    gate_errors: List[str] = []
    acceptance_targets: Dict[str, float] = {}
    if args.require_acceptance:
        config = yaml.safe_load(args.targets_config.read_text(encoding="utf-8")) or {}
        training_cfg = config.get("training", {})
        acceptance_languages = [
            str(language).strip().lower()
            for language in config.get("data", {}).get("accepted_languages", [])
            if str(language).strip()
        ]
        if acceptance_languages:
            acceptance_indices = [
                index
                for index, record in enumerate(evaluable)
                if (record.language or "").strip().lower() in acceptance_languages
            ]
            if not acceptance_indices:
                print(
                    "No records match configured acceptance languages: "
                    + ", ".join(acceptance_languages),
                    file=sys.stderr,
                )
                return 2
            acceptance_summary = summarize_metrics(
                [y_true[index] for index in acceptance_indices],
                [y_pred[index] for index in acceptance_indices],
                LABEL_ORDER,
            )
        checks = {
            "transaction_recall": (
                float(acceptance_summary["per_class"]["TRANSACTION"]["recall"]),
                float(training_cfg.get("target_transaction_recall", 0.985)),
            ),
            "transaction_precision": (
                float(acceptance_summary["per_class"]["TRANSACTION"]["precision"]),
                float(training_cfg.get("min_transaction_precision", 0.92)),
            ),
            "macro_f1": (
                float(acceptance_summary["macro_f1"]),
                float(training_cfg.get("min_macro_f1", 0.86)),
            ),
            "harass_f1": (
                float(acceptance_summary["per_class"]["HARASS"]["f1"]),
                float(training_cfg.get("min_harass_f1", 0.80)),
            ),
            "fraud_recall": (
                float(acceptance_summary["per_class"]["FRAUD"]["recall"]),
                float(training_cfg.get("min_fraud_recall", 0.80)),
            ),
        }
        acceptance_targets = {
            name: required for name, (_, required) in checks.items()
        }
        gate_errors = [
            f"{name}={actual:.6f} < {required:.6f}"
            for name, (actual, required) in checks.items()
            if actual < required
        ]

    txn_idx = LABEL_ORDER.index("TRANSACTION")
    matrix = acceptance_summary["confusion_matrix"]
    txn_tp = int(matrix[txn_idx][txn_idx])
    txn_total = int(sum(matrix[txn_idx]))
    transaction_safety: Optional[Dict[str, object]] = None
    if protection_decisions:
        scoped = [
            (evaluable[index], protection_decisions[index])
            for index in acceptance_indices
        ]
        true_transactions = [
            decision
            for record, decision in scoped
            if record.label == "TRANSACTION"
        ]
        non_transactions = [
            decision
            for record, decision in scoped
            if record.label != "TRANSACTION"
        ]
        safe_transaction_count = sum(
            decision.action in {"INBOX", "REVIEW"}
            for decision in true_transactions
        )
        collateral_inbox_count = sum(
            decision.action == "INBOX"
            for decision in non_transactions
        )
        transaction_safety = {
            "definition": (
                "A true transaction is safe when routed to INBOX or REVIEW; "
                "category remains the primary four-class model output."
            ),
            "transaction_count": len(true_transactions),
            "safe_transaction_count": safe_transaction_count,
            "transaction_safe_recall": (
                safe_transaction_count / len(true_transactions)
                if true_transactions
                else 0.0
            ),
            "transaction_safe_recall_ci95": wilson_interval(
                safe_transaction_count,
                len(true_transactions),
            ),
            "non_transaction_count": len(non_transactions),
            "collateral_inbox_count": collateral_inbox_count,
            "collateral_inbox_rate": (
                collateral_inbox_count / len(non_transactions)
                if non_transactions
                else 0.0
            ),
        }

    report: Dict[str, object] = {
        "seed": args.seed,
        "stage": args.stage,
        "classifier": classifier,
        "mode": mode,
        "model_path": model_path_str,
        "test_count": len(records),
        "evaluated_count": len(evaluable),
        "needs_review_count": len(needs_review),
        "prediction_distribution": pred_dist,
        "metrics": summary,
        "per_language": per_language_metrics(evaluable, y_true, y_pred),
        "acceptance_scope": {
            "languages": acceptance_languages or "all",
            "metrics": acceptance_summary,
        },
        "transaction_recall": acceptance_summary["per_class"]["TRANSACTION"]["recall"],
        "transaction_precision": acceptance_summary["per_class"]["TRANSACTION"]["precision"],
        "transaction_recall_ci95": wilson_interval(txn_tp, txn_total),
        "macro_f1": acceptance_summary["macro_f1"],
        "acceptance_targets": acceptance_targets,
        "gate_errors": gate_errors,
        "acceptance_passed": args.require_acceptance and not gate_errors,
        "transaction_protection": {
            "enabled": mode == "pipeline",
            "rules_dir": (
                str(args.rules_dir).replace("\\", "/")
                if mode == "pipeline"
                else None
            ),
            "model_head_positive_count": sum(model_protection_flags),
            "protected_count": sum(
                decision.protected for decision in protection_decisions
            ),
            "fraud_conflict_count": sum(
                decision.fraud_conflict for decision in protection_decisions
            ),
            "safety_metrics": transaction_safety,
            "raw_metrics": (
                summarize_metrics(
                    y_true,
                    raw_predictions,
                    LABEL_ORDER,
                )
                if raw_predictions is not None and mode == "pipeline"
                else None
            ),
        },
        "claim_allowed": False,
        "claim_note": (
            "Synthetic or small frozen sets must not claim transaction recall ≥98%. "
            "Only a dual-annotated real freeze with matching SHA may claim PASS."
        ),
        "review_semantics": {
            "NEEDS_REVIEW": (
                "Ambiguous or policy-escalation label excluded from training and "
                "macro metrics. On-device routing may send low-confidence or "
                "conflicting-rule messages to human review instead of forcing a "
                "four-class prediction."
            ),
            "excluded_from_training": ["NEEDS_REVIEW"],
            "production_labels": list(LABEL_ORDER),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.error_samples > 0:
        error_path = args.error_output or args.output.with_name(
            f"{args.output.stem}_errors.json"
        )
        errors = [
            {
                "id": record.id,
                "text": record.text,
                "true_label": truth,
                "predicted_label": prediction,
            }
            for record, truth, prediction in zip(evaluable, y_true, y_pred)
            if truth != prediction
        ][: args.error_samples]
        error_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(
            json.dumps(errors, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(f"Wrote evaluation to {args.output}")
    print(
        f"mode={mode} macro_f1={summary['macro_f1']:.3f} "
        f"transaction_recall={summary['per_class']['TRANSACTION']['recall']:.3f} "
        f"pred_dist={pred_dist}"
    )
    # Collapse gate: all predictions one class → non-zero exit for pipeline.
    if len(pred_dist) == 1 and len(evaluable) >= 8:
        print(
            "FAIL: model collapsed to a single predicted class — "
            "do not export/quantize this checkpoint.",
            file=sys.stderr,
        )
        return 3
    if gate_errors:
        print(
            "FAIL: validation pipeline targets not met:\n  - "
            + "\n  - ".join(gate_errors),
            file=sys.stderr,
        )
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
