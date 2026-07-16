#!/usr/bin/env python3
"""Evaluate classifier on frozen test set.

Modes:
  tflite   — TFLite student model (default when model exists)
  rule     — rule heuristics only (explicit; must not be mistaken for model metrics)
  predictions — external predictions JSONL
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SEED = 42

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
from src.byte_encoder import encode_text  # noqa: E402
from src.metrics import summarize_metrics, wilson_interval  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import LABEL_ORDER, load_jsonl  # noqa: E402
from src.train_utils import set_seed  # noqa: E402

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
        choices=["auto", "tflite", "rule", "predictions"],
        default="auto",
        help="Evaluation path. auto prefers TFLite when present.",
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


def tflite_predict_batch(model_path: Path, texts: Sequence[str]) -> List[str]:
    import numpy as np
    import tensorflow as tf

    interpreter = tf.lite.Interpreter(model_content=model_path.read_bytes())
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()[0]
    output_details = interpreter.get_output_details()[0]
    preds: List[str] = []
    for text in texts:
        ids = encode_text(normalize_text(text), length=512)
        inp = np.asarray([ids], dtype=input_details["dtype"])
        interpreter.set_tensor(input_details["index"], inp)
        interpreter.invoke()
        out = interpreter.get_tensor(output_details["index"])[0]
        if out.dtype != np.float32 and out.dtype != np.float64:
            # INT8 logits: pick argmax on quantized values (monotonic for same scale).
            idx = int(np.argmax(out))
        else:
            idx = int(np.argmax(out))
        preds.append(LABEL_ORDER[idx])
    return preds


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
        elif resolve_tflite(args.tflite) is not None:
            mode = "tflite"
        else:
            print(
                "No TFLite model found. Refusing to silently use rule heuristics as "
                "model metrics. Pass --mode rule explicitly if that is intended.",
                file=sys.stderr,
            )
            return 1

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
    else:
        model_path = resolve_tflite(args.tflite)
        if model_path is None:
            print("TFLite model not found.", file=sys.stderr)
            return 1
        try:
            y_pred = tflite_predict_batch(model_path, [r.text for r in evaluable])
        except ImportError:
            print(
                "TensorFlow required for --mode tflite. "
                "Install per docs/异机测试环境安装清单.md",
                file=sys.stderr,
            )
            return 2
        classifier = "tflite"
        try:
            model_path_str = str(model_path.relative_to(ROOT.parent)).replace("\\", "/")
        except ValueError:
            model_path_str = str(model_path).replace("\\", "/")

    y_true = [r.label for r in evaluable]
    summary = summarize_metrics(y_true, y_pred, LABEL_ORDER)
    pred_dist = dict(Counter(y_pred))

    txn_idx = LABEL_ORDER.index("TRANSACTION")
    matrix = summary["confusion_matrix"]
    txn_tp = int(matrix[txn_idx][txn_idx])
    txn_total = int(sum(matrix[txn_idx]))

    report: Dict[str, object] = {
        "seed": args.seed,
        "classifier": classifier,
        "mode": mode,
        "model_path": model_path_str,
        "test_count": len(records),
        "evaluated_count": len(evaluable),
        "needs_review_count": len(needs_review),
        "prediction_distribution": pred_dist,
        "metrics": summary,
        "per_language": per_language_metrics(evaluable, y_true, y_pred),
        "transaction_recall": summary["per_class"]["TRANSACTION"]["recall"],
        "transaction_precision": summary["per_class"]["TRANSACTION"]["precision"],
        "transaction_recall_ci95": wilson_interval(txn_tp, txn_total),
        "macro_f1": summary["macro_f1"],
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
