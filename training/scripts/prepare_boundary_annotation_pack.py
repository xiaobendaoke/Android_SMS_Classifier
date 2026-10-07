#!/usr/bin/env python3
"""Prepare blind, TRAIN-only transaction/HARASS boundary annotation sheets."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.schema import LABEL_ORDER  # noqa: E402
from src.split_groups import connected_group_ids, template_fingerprint  # noqa: E402
from src.train_utils import (  # noqa: E402
    filter_records_by_languages,
    load_labeled_records,
    records_to_xy,
    split_student_logits,
)

DEFAULT_OUT = ROOT / "data" / "interim" / "annotation" / "boundary_v1"
DEFAULT_MANIFEST = ROOT / "data" / "manifests" / "boundary_annotation_v1.json"
BUCKET_QUOTAS = {
    "TRANSACTION_HARD_POSITIVE": 200,
    "TRANSACTION_HARD_NEGATIVE": 250,
    "HARASS_HARD_POSITIVE": 150,
    "HARASS_HARD_NEGATIVE": 150,
}
FIELDS = [
    "id",
    "text",
    "source",
    "template_group",
    "sender_group",
    "boundary_bucket",
    "prior_label",
    "teacher_prediction",
    "teacher_transaction_score",
    "teacher_harass_score",
    "student_prediction",
    "student_transaction_score",
    "student_harass_score",
    "label",
    "human_annotator_id",
    "notes",
]
BLIND_FIELDS = {
    "boundary_bucket",
    "prior_label",
    "teacher_prediction",
    "teacher_transaction_score",
    "teacher_harass_score",
    "student_prediction",
    "student_transaction_score",
    "student_harass_score",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values, axis=1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / np.sum(exponent, axis=1, keepdims=True)


def write_csv(path: Path, rows: Sequence[dict], *, blind: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for source in rows:
            row = dict(source)
            if blind:
                for field in BLIND_FIELDS:
                    row[field] = ""
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def load_teacher_logits(manifest_path: Path) -> Dict[str, np.ndarray]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    logits_path = ROOT / manifest["path"]
    data = np.load(logits_path, allow_pickle=True)
    ids = [str(value) for value in data["ids"].tolist()]
    logits = np.asarray(data["logits"], dtype=np.float32)
    if logits.shape != (len(ids), len(LABEL_ORDER)):
        raise ValueError(f"Unexpected teacher logits shape: {logits.shape}")
    return {record_id: logits[index] for index, record_id in enumerate(ids)}


def select_diverse(
    candidates: Sequence[tuple[float, int]],
    *,
    quota: int,
    records,
    component_ids: Sequence[str],
    used_components: set[str],
    used_fingerprints: set[str],
) -> List[int]:
    selected: List[int] = []
    for _, index in sorted(candidates, key=lambda item: (-item[0], records[item[1]].id)):
        record = records[index]
        component_id = component_ids[index]
        fingerprint = template_fingerprint(record.text)
        if component_id in used_components or fingerprint in used_fingerprints:
            continue
        selected.append(index)
        used_components.add(component_id)
        used_fingerprints.add(fingerprint)
        if len(selected) >= quota:
            break
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--train",
        type=Path,
        default=ROOT / "data" / "processed" / "train.jsonl",
    )
    parser.add_argument(
        "--student",
        type=Path,
        default=ROOT / "artifacts" / "student" / "sms_bytecnn_fp32.keras",
    )
    parser.add_argument(
        "--teacher-logits-manifest",
        type=Path,
        default=ROOT / "data" / "manifests" / "teacher_logits_manifest.json",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    import tensorflow as tf

    records = filter_records_by_languages(
        load_labeled_records(args.train),
        ["zh"],
    )
    records = [
        record
        for record in records
        if record.split == "train"
        and not record.is_synthetic
        and not record.is_adversarial
    ]
    if not records:
        print("No eligible Chinese TRAIN records.", file=sys.stderr)
        return 1

    teacher_map = load_teacher_logits(args.teacher_logits_manifest)
    missing_teacher = [record.id for record in records if record.id not in teacher_map]
    if missing_teacher:
        print(
            f"Teacher logits missing for {len(missing_teacher)} TRAIN rows.",
            file=sys.stderr,
        )
        return 2
    teacher_logits = np.stack([teacher_map[record.id] for record in records])
    teacher_probs = softmax(teacher_logits)

    model = tf.keras.models.load_model(args.student)
    max_bytes = int(model.input_shape[-1])
    x, _ = records_to_xy(records, max_bytes=max_bytes)
    student_outputs = np.asarray(model.predict(x, batch_size=128, verbose=0))
    student_logits, _ = split_student_logits(student_outputs)
    student_probs = softmax(student_logits)

    txn_index = LABEL_ORDER.index("TRANSACTION")
    harass_index = LABEL_ORDER.index("HARASS")
    teacher_predictions = np.argmax(teacher_logits, axis=1)
    student_predictions = np.argmax(student_logits, axis=1)
    component_ids = connected_group_ids(records)

    bucket_candidates: Dict[str, List[tuple[float, int]]] = {
        bucket: [] for bucket in BUCKET_QUOTAS
    }
    for index, record in enumerate(records):
        teacher_txn = float(teacher_probs[index, txn_index])
        student_txn = float(student_probs[index, txn_index])
        teacher_harass = float(teacher_probs[index, harass_index])
        student_harass = float(student_probs[index, harass_index])
        average_txn = (teacher_txn + student_txn) / 2.0
        average_harass = (teacher_harass + student_harass) / 2.0
        teacher_pred = LABEL_ORDER[int(teacher_predictions[index])]
        student_pred = LABEL_ORDER[int(student_predictions[index])]

        if record.label == "TRANSACTION":
            difficulty = 1.0 - average_txn
            difficulty += 0.25 * (
                teacher_pred != "TRANSACTION" or student_pred != "TRANSACTION"
            )
            bucket_candidates["TRANSACTION_HARD_POSITIVE"].append(
                (difficulty, index)
            )
        else:
            difficulty = average_txn
            difficulty += 0.25 * (
                teacher_pred == "TRANSACTION" or student_pred == "TRANSACTION"
            )
            bucket_candidates["TRANSACTION_HARD_NEGATIVE"].append(
                (difficulty, index)
            )

        if record.label == "HARASS":
            difficulty = 1.0 - average_harass
            difficulty += 0.25 * (
                teacher_pred != "HARASS" or student_pred != "HARASS"
            )
            bucket_candidates["HARASS_HARD_POSITIVE"].append(
                (difficulty, index)
            )
        else:
            difficulty = average_harass
            difficulty += 0.25 * (
                teacher_pred == "HARASS" or student_pred == "HARASS"
            )
            bucket_candidates["HARASS_HARD_NEGATIVE"].append(
                (difficulty, index)
            )

    selected_rows: List[dict] = []
    selected_components: set[str] = set()
    selected_fingerprints: set[str] = set()
    coverage: Dict[str, dict] = {}
    for bucket, quota in BUCKET_QUOTAS.items():
        selected = select_diverse(
            bucket_candidates[bucket],
            quota=quota,
            records=records,
            component_ids=component_ids,
            used_components=selected_components,
            used_fingerprints=selected_fingerprints,
        )
        coverage[bucket] = {
            "target": quota,
            "selected": len(selected),
            "candidate_count": len(bucket_candidates[bucket]),
            "shortfall": max(0, quota - len(selected)),
        }
        for index in selected:
            record = records[index]
            selected_rows.append(
                {
                    "id": record.id,
                    "text": record.text,
                    "source": record.source,
                    "template_group": record.template_group,
                    "sender_group": record.sender_group,
                    "boundary_bucket": bucket,
                    "prior_label": record.label,
                    "teacher_prediction": LABEL_ORDER[
                        int(teacher_predictions[index])
                    ],
                    "teacher_transaction_score": (
                        f"{teacher_probs[index, txn_index]:.8f}"
                    ),
                    "teacher_harass_score": (
                        f"{teacher_probs[index, harass_index]:.8f}"
                    ),
                    "student_prediction": LABEL_ORDER[
                        int(student_predictions[index])
                    ],
                    "student_transaction_score": (
                        f"{student_probs[index, txn_index]:.8f}"
                    ),
                    "student_harass_score": (
                        f"{student_probs[index, harass_index]:.8f}"
                    ),
                    "label": "",
                    "human_annotator_id": "",
                    "notes": "",
                    "component_id": component_ids[index],
                }
            )
    selected_rows.sort(key=lambda row: (row["boundary_bucket"], row["id"]))
    shortfall = sum(item["shortfall"] for item in coverage.values())
    if shortfall:
        print(
            "Insufficient component-diverse candidates:\n"
            + json.dumps(coverage, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 3

    pool_path = args.out_dir / "boundary_pool.csv"
    a_path = args.out_dir / "boundary_annotator_A.csv"
    b_path = args.out_dir / "boundary_annotator_B.csv"
    write_csv(pool_path, selected_rows, blind=False)
    write_csv(a_path, selected_rows, blind=True)
    write_csv(b_path, selected_rows, blind=True)

    manifest = {
        "version": "1.0.0",
        "status": "PENDING_DUAL_HUMAN_ANNOTATION",
        "claim_allowed": False,
        "source_split": "train",
        "locked_validation_or_test_read": False,
        "selected_total": len(selected_rows),
        "coverage": coverage,
        "source_distribution": dict(
            Counter(row["source"] for row in selected_rows)
        ),
        "ids": [row["id"] for row in selected_rows],
        "component_ids": sorted(selected_components),
        "pool_path": str(pool_path.relative_to(ROOT)).replace("\\", "/"),
        "pool_sha256": sha256_file(pool_path),
        "annotator_a_path": str(a_path.relative_to(ROOT)).replace("\\", "/"),
        "annotator_b_path": str(b_path.relative_to(ROOT)).replace("\\", "/"),
        "student_model_sha256": sha256_file(args.student),
        "teacher_logits_manifest_sha256": sha256_file(
            args.teacher_logits_manifest
        ),
        "note": (
            "Rows come only from the current TRAIN split. Do not run another "
            "training experiment until dual annotation, adjudication, and the "
            "label-correction overlay are complete."
        ),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "selected_total": manifest["selected_total"],
                "coverage": coverage,
                "annotator_a_path": manifest["annotator_a_path"],
                "annotator_b_path": manifest["annotator_b_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
