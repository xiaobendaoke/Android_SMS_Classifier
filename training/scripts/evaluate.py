#!/usr/bin/env python3
"""Evaluate classifier on frozen test set."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SEED = 42

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))
from src.metrics import summarize_metrics, wilson_interval  # noqa: E402
from src.normalize import normalize_text  # noqa: E402
from src.schema import LABEL_ORDER, load_jsonl  # noqa: E402

# Rule heuristics aligned with Android rule engine patterns (pure Python).
RULE_PATTERNS: List[Tuple[str, str, int]] = [
    ("TRANSACTION", r"(?:入账|扣款|payment|pembayaran|भुगतान|订单|flight|shipped|ticket|deposit)", 80),
    ("AD", r"(?:优惠|promo|diskon|click|prize|sale|इनाम|gratis|offer|discount|抽奖)", 70),
    ("HARASS", r"(?:还钱|pay me|utang|परेशान|abai|contact|harass|terus hubungi)", 75),
    ("FRAUD", r"(?:异常|verify|http|blocked|diblokir|ब्लॉक|phish|OTP|冻结|locked|refund pending)", 90),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate model on frozen test set.")
    parser.add_argument(
        "--test",
        type=Path,
        default=ROOT / "data" / "processed" / "test.jsonl",
        help="Frozen test JSONL.",
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
    """Score-based rule heuristic classifier."""
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


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.test.exists():
        print(f"Test set missing: {args.test}", file=sys.stderr)
        return 1

    records = load_jsonl(args.test)
    evaluable = [r for r in records if r.label in LABEL_ORDER]
    needs_review = [r for r in records if r.label == "NEEDS_REVIEW"]

    if args.predictions and args.predictions.exists():
        pred_map = load_predictions(args.predictions)
        y_pred = [pred_map.get(r.id, rule_predict(r.text)) for r in evaluable]
        classifier = "predictions_file"
    else:
        y_pred = [rule_predict(r.text) for r in evaluable]
        classifier = "rule_heuristics"

    y_true = [r.label for r in evaluable]
    summary = summarize_metrics(y_true, y_pred, LABEL_ORDER)

    txn_idx = LABEL_ORDER.index("TRANSACTION")
    matrix = summary["confusion_matrix"]
    txn_tp = int(matrix[txn_idx][txn_idx])
    txn_total = int(sum(matrix[txn_idx]))

    report: Dict[str, object] = {
        "seed": args.seed,
        "classifier": classifier,
        "test_count": len(records),
        "evaluated_count": len(evaluable),
        "needs_review_count": len(needs_review),
        "metrics": summary,
        "transaction_recall": summary["per_class"]["TRANSACTION"]["recall"],
        "transaction_recall_ci95": wilson_interval(txn_tp, txn_total),
        "macro_f1": summary["macro_f1"],
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
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote evaluation to {args.output}")
    print(
        f"macro_f1={summary['macro_f1']:.3f} "
        f"transaction_recall={summary['per_class']['TRANSACTION']['recall']:.3f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
