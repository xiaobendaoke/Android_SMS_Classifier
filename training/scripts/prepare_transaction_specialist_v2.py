#!/usr/bin/env python3
"""Prepare blank dual-human blind packs for the 600-row transaction specialist set.

AI may only create empty sheets. Never fill HUMAN labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GUIDE_PATH = ROOT.parent / "docs" / "labeling-guide.md"
OUTPUT_DIR = ROOT / "data" / "interim" / "annotation" / "transaction_specialist_v2"
BLIND_FIELDS = [
    "review_id",
    "id",
    "text",
    "label",
    "notes",
    "human_annotator_id",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_review_order(rows: Sequence[dict]) -> str:
    return hashlib.sha256(
        "\n".join(str(row["review_id"]) for row in rows).encode("utf-8")
    ).hexdigest()


def write_csv(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def load_specialist_texts() -> List[Dict[str, str]]:
    """Load specialist bodies without exposing labels/subtypes to blind sheets."""
    candidates = [
        ROOT
        / "data"
        / "interim"
        / "annotation"
        / "transaction_specialist"
        / "transaction_specialist_frozen.jsonl",
        ROOT
        / "data"
        / "interim"
        / "annotation"
        / "transaction_specialist"
        / "transaction_specialist_pool.csv",
    ]
    holdout = ROOT / "data" / "manifests" / "transaction_specialist_holdout.json"
    holdout_ids = []
    if holdout.exists():
        payload = json.loads(holdout.read_text(encoding="utf-8"))
        holdout_ids = [str(item) for item in payload.get("ids", [])]

    for path in candidates:
        if not path.exists():
            continue
        rows: List[Dict[str, str]] = []
        if path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                rows.append({"id": str(item["id"]), "text": str(item["text"])})
        else:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    rows.append(
                        {"id": str(row["id"]), "text": str(row.get("text", ""))}
                    )
        if holdout_ids:
            by_id = {row["id"]: row for row in rows}
            ordered = []
            missing = []
            for rid in holdout_ids:
                if rid in by_id:
                    ordered.append(by_id[rid])
                else:
                    missing.append(rid)
            if missing:
                raise SystemExit(
                    "Specialist texts missing for holdout ids: "
                    + ", ".join(missing[:20])
                )
            if len(ordered) != 600:
                raise SystemExit(f"Expected 600 specialist rows, found {len(ordered)}")
            return ordered
        if len(rows) != 600:
            raise SystemExit(f"Expected 600 specialist rows, found {len(rows)}")
        return rows
    raise SystemExit("No specialist text source found for v2 blind pack.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare transaction_specialist_v2 blank A/B packs."
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    source_rows = load_specialist_texts()
    # Stable review_id independent of A/B shuffle order.
    base = []
    for index, row in enumerate(source_rows, start=1):
        base.append(
            {
                "review_id": f"tsx-v2-{index:04d}",
                "id": row["id"],
                "text": row["text"],
                "label": "",
                "notes": "",
                "human_annotator_id": "",
            }
        )

    rng_a = random.Random(args.seed)
    rng_b = random.Random(args.seed + 1)
    order_a = list(range(len(base)))
    order_b = list(range(len(base)))
    rng_a.shuffle(order_a)
    rng_b.shuffle(order_b)
    sheet_a = [base[i] for i in order_a]
    sheet_b = [base[i] for i in order_b]
    if [row["review_id"] for row in sheet_a] == [row["review_id"] for row in sheet_b]:
        # Extremely unlikely with different seeds; force a swap if identical.
        if len(sheet_b) > 1:
            sheet_b[0], sheet_b[1] = sheet_b[1], sheet_b[0]

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    internal_path = out / "specialist_pool_internal.csv"
    a_path = out / "specialist_annotator_A.csv"
    b_path = out / "specialist_annotator_B.csv"
    write_csv(
        internal_path,
        [
            {
                "review_id": row["review_id"],
                "id": row["id"],
                "text": row["text"],
            }
            for row in base
        ],
        ["review_id", "id", "text"],
    )
    write_csv(a_path, sheet_a, BLIND_FIELDS)
    write_csv(b_path, sheet_b, BLIND_FIELDS)

    guide_sha = sha256_file(GUIDE_PATH) if GUIDE_PATH.exists() else None
    holdout = ROOT / "data" / "manifests" / "transaction_specialist_holdout.json"
    manifest = {
        "version": "2.0.0",
        "status": "PENDING_DUAL_HUMAN_ANNOTATION",
        "claim_allowed": False,
        "dual_human_evidence_complete": False,
        "seed": args.seed,
        "annotation_guide_sha256": guide_sha,
        "model_scores_used": False,
        "test_text_exposed": False,
        "independence_attestation": {
            "required": True,
            "present": False,
            "note": (
                "Two real humans must independently complete A/B. "
                "AI must not fill HUMAN labels."
            ),
        },
        "dual_human_evidence": {
            "independence_attestation": None,
            "started_at": None,
            "completed_at": None,
            "annotator_roster_internal_ref": None,
            "saw_model_suggestions": None,
        },
        "annotator_ids": {"A": "PENDING_ASSIGNMENT", "B": "PENDING_ASSIGNMENT"},
        "counts": {"pool_rows": len(base)},
        "blind_fields": BLIND_FIELDS,
        "forbidden_blind_fields": [
            "prior_label",
            "subtype",
            "source_label",
            "model_prediction",
            "confidence",
            "annotator_a_label",
            "annotator_b_label",
            "adjudicated_label",
        ],
        "source_holdout_manifest": (
            str(holdout.relative_to(ROOT)).replace("\\", "/") if holdout.exists() else None
        ),
        "source_holdout_sha256": sha256_file(holdout) if holdout.exists() else None,
        "files": {
            "internal_pool": {
                "path": str(internal_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(internal_path),
            },
            "annotator_a": {
                "path": str(a_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(a_path),
                "review_order_sha256": sha256_review_order(sheet_a),
            },
            "annotator_b": {
                "path": str(b_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(b_path),
                "review_order_sha256": sha256_review_order(sheet_b),
            },
        },
        "allowed_labels": [
            "TRANSACTION",
            "AD",
            "HARASS",
            "FRAUD",
            "NEEDS_REVIEW",
        ],
        "note": (
            "Blind sheets omit prior labels/subtypes/history/model scores. "
            "Humans fill label/notes/human_annotator_id only."
        ),
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "pool_rows": len(base),
                "output_dir": str(out.relative_to(ROOT)).replace("\\", "/"),
                "claim_allowed": False,
                "orders_differ": [row["review_id"] for row in sheet_a]
                != [row["review_id"] for row in sheet_b],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
