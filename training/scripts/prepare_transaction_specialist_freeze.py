#!/usr/bin/env python3
"""Reserve a diverse Chinese transaction specialist set for dual human review.

This script samples records already labeled TRANSACTION; subtype regexes are
used only for coverage sampling and never assign or change the four-class label.
The generated set is NOT claimable until two humans label it independently.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.schema import SmsRecord, load_jsonl  # noqa: E402
from src.split_groups import connected_group_ids, template_fingerprint  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
OUT_DIR = ROOT / "data" / "interim" / "annotation" / "transaction_specialist"
HOLDOUT_MANIFEST = ROOT / "data" / "manifests" / "transaction_specialist_holdout.json"

SUBTYPE_PATTERNS = {
    "OTP": re.compile(r"验证码|校验码|动态密码|短信密码|认证码|登录码", re.I),
    "LOGISTICS": re.compile(r"快递|包裹|取件|驿站|派送|物流|运单", re.I),
    "ORDER": re.compile(r"订单|下单|退款|退货|预订|预约|出票|车票|航班", re.I),
    "REPAYMENT": re.compile(r"还款|账单|应还|欠款|逾期|分期|贷款|房贷|车贷", re.I),
    "CARRIER": re.compile(r"移动|联通|电信|运营商|话费|流量|套餐|停机|宽带|实名", re.I),
    "BANK": re.compile(r"银行|账户|银行卡|信用卡|借记卡|入账|到账|扣款|消费|余额|转账", re.I),
}
SUBTYPE_ORDER = tuple(SUBTYPE_PATTERNS)
AUTOMATED_REVIEW_MARKERS = (
    "deepseek",
    "llm",
    "audit",
    "script",
    "patch",
    "repair",
    "fix",
    "agent",
)
FIELDS = [
    "id",
    "text",
    "source",
    "template_group",
    "sender_group",
    "coverage_subtype",
    "prior_label",
    "label",
    "human_annotator_id",
    "notes",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a >=500-row Chinese TRANSACTION dual-human freeze queue."
    )
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--holdout-manifest", type=Path, default=HOLDOUT_MANIFEST)
    parser.add_argument("--per-subtype", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def load_processed(processed_dir: Path) -> List[SmsRecord]:
    records: List[SmsRecord] = []
    for split_name in ("train", "validation", "test"):
        path = processed_dir / f"{split_name}.jsonl"
        if path.exists():
            records.extend(load_jsonl(path))
    return records


def coverage_subtype(text: str) -> Optional[str]:
    """Choose one coverage bucket; does not infer the SMS class label."""
    for subtype in SUBTYPE_ORDER:
        if SUBTYPE_PATTERNS[subtype].search(text):
            return subtype
    return None


def is_human_annotator(identifier: str) -> bool:
    lowered = identifier.strip().lower()
    return bool(lowered) and not any(marker in lowered for marker in AUTOMATED_REVIEW_MARKERS)


def select_records(
    records: Sequence[SmsRecord],
    *,
    per_subtype: int,
    seed: int,
) -> tuple[List[dict], Dict[str, dict]]:
    component_ids = connected_group_ids(records)
    buckets: Dict[str, List[tuple[SmsRecord, str]]] = defaultdict(list)
    for idx, record in enumerate(records):
        if (
            record.language != "zh"
            or record.label != "TRANSACTION"
            or record.is_synthetic
            or record.is_adversarial
        ):
            continue
        subtype = coverage_subtype(record.text)
        if subtype:
            buckets[subtype].append((record, component_ids[idx]))

    rng = random.Random(seed)
    selected: List[dict] = []
    selected_components = set()
    coverage: Dict[str, dict] = {}
    for subtype in SUBTYPE_ORDER:
        candidates = list(buckets[subtype])
        rng.shuffle(candidates)
        candidates.sort(
            key=lambda item: (
                template_fingerprint(item[0].text),
                item[0].template_group,
                item[0].id,
            )
        )
        chosen = []
        seen_fingerprints = set()
        # First pass maximizes independent templates/components.
        for record, component_id in candidates:
            fingerprint = template_fingerprint(record.text)
            if component_id in selected_components or fingerprint in seen_fingerprints:
                continue
            chosen.append((record, component_id))
            selected_components.add(component_id)
            seen_fingerprints.add(fingerprint)
            if len(chosen) >= per_subtype:
                break
        coverage[subtype] = {
            "available_rows": len(candidates),
            "selected": len(chosen),
            "target": per_subtype,
            "shortfall": max(0, per_subtype - len(chosen)),
        }
        for record, component_id in chosen:
            review_ids = sorted(set(record.annotator_ids))
            selected.append(
                {
                    "id": record.id,
                    "text": record.text,
                    "source": record.source,
                    "template_group": record.template_group,
                    "sender_group": record.sender_group,
                    "coverage_subtype": subtype,
                    "prior_label": record.label,
                    "label": "",
                    "human_annotator_id": "",
                    "notes": "Re-label independently using docs/labeling-guide.md",
                    "component_id": component_id,
                    "existing_review_ids": review_ids,
                    "existing_human_review_ids": [
                        item for item in review_ids if is_human_annotator(item)
                    ],
                }
            )
    selected.sort(key=lambda row: (row["coverage_subtype"], row["id"]))
    return selected, coverage


def write_csv(path: Path, rows: Sequence[dict], *, blind: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            item = dict(row)
            if blind:
                item["coverage_subtype"] = ""
                item["prior_label"] = ""
            writer.writerow({field: item.get(field, "") for field in FIELDS})


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    records = load_processed(args.processed_dir)
    if not records:
        print(f"No processed records under {args.processed_dir}", file=sys.stderr)
        return 1
    selected, coverage = select_records(
        records,
        per_subtype=args.per_subtype,
        seed=args.seed,
    )
    target_total = args.per_subtype * len(SUBTYPE_ORDER)
    if len(selected) < target_total:
        print(
            f"Insufficient diverse transaction records: {len(selected)}/{target_total}",
            file=sys.stderr,
        )
        print(json.dumps(coverage, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pool_path = args.out_dir / "transaction_specialist_pool.csv"
    annotator_a_path = args.out_dir / "transaction_specialist_annotator_A.csv"
    annotator_b_path = args.out_dir / "transaction_specialist_annotator_B.csv"
    write_csv(pool_path, selected, blind=False)
    write_csv(annotator_a_path, selected, blind=True)
    write_csv(annotator_b_path, selected, blind=True)

    human_counts = Counter(
        len(row["existing_human_review_ids"]) for row in selected
    )
    manifest = {
        "version": "1.0.0",
        "status": "PENDING_DUAL_HUMAN_ANNOTATION",
        "claim_allowed": False,
        "seed": args.seed,
        "target_total": target_total,
        "selected_total": len(selected),
        "coverage": coverage,
        "ids": [row["id"] for row in selected],
        "component_ids": sorted({row["component_id"] for row in selected}),
        "pool_path": str(pool_path.relative_to(ROOT)).replace("\\", "/"),
        "pool_sha256": sha256_file(pool_path),
        "annotator_a_path": str(annotator_a_path.relative_to(ROOT)).replace("\\", "/"),
        "annotator_b_path": str(annotator_b_path.relative_to(ROOT)).replace("\\", "/"),
        "existing_human_review_count_distribution": dict(human_counts),
        "claim_note": (
            "Existing annotator_ids are automated audit pipeline identifiers, not "
            "two human annotators. Two humans must independently complete A/B sheets; "
            "agreements are merged and conflicts adjudicated before status may become FROZEN."
        ),
    }
    args.holdout_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.holdout_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote transaction specialist pool: {pool_path} ({len(selected)} rows)")
    print(f"Wrote blind annotator sheets: {annotator_a_path}, {annotator_b_path}")
    print(f"Wrote holdout manifest: {args.holdout_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
