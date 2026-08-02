#!/usr/bin/env python3
"""Prepare blind dual-annotator review packs for label conflicts.

AI may generate the task pack but must never fill HUMAN labels.
Blind sheets contain only: review_group_id, id, text, label, notes, human_annotator_id.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.schema import SmsRecord, load_jsonl  # noqa: E402
from src.split_groups import connected_group_ids, template_fingerprint  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "interim" / "annotation" / "label_conflicts_v2"
GUIDE_PATH = ROOT.parent / "docs" / "labeling-guide.md"

BLIND_FIELDS = [
    "review_group_id",
    "id",
    "text",
    "label",
    "notes",
    "human_annotator_id",
]

HARDCODED_REVIEW_IDS = {
    "zh_08937",
    "zh-n2w-07703",
    "zh-n2w-07929",
    "zh-n2w-09673",
    "zh-n2w-03416",
    "zh-n2w-06672",
    "zh-n2w-07304",
    "zh-n2w-07558",
    "zh-n2w-07605",
    "zh-n2w-07617",
    "zh-n2w-07725",
    "zh-n2w-07978",
    "zh-n2w-08206",
    "zh-n2w-07310",
    "zh_10548",
    "zh_01214",
    "zh-n2w-06829",
    "zh-n2w-04902",
    "zh-n2w-08728",
    "zh-n2w-08886",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_review_order(rows: Sequence[dict]) -> str:
    return hashlib.sha256(
        "\n".join(str(row["review_group_id"]) for row in rows).encode("utf-8")
    ).hexdigest()


def write_csv(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def hard_identity_tokens(record: SmsRecord) -> Iterable[str]:
    """Identity without fingerprint — used for hard component conflicts."""
    yield f"template:{record.template_group}"
    yield f"sender:{record.sender_group}"
    yield f"family:{record.id}"
    if record.parent_id:
        yield f"family:{record.parent_id}"


def hard_component_ids(records: Sequence[SmsRecord]) -> Dict[int, str]:
    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    first: Dict[str, int] = {}
    for idx, record in enumerate(records):
        for token in hard_identity_tokens(record):
            prev = first.setdefault(token, idx)
            union(idx, prev)
    mapping: Dict[int, str] = {}
    members: Dict[int, List[int]] = defaultdict(list)
    for idx in range(len(records)):
        members[find(idx)].append(idx)
    for indices in members.values():
        sig = sorted(records[i].id for i in indices)
        digest = hashlib.sha256("\n".join(sig).encode("utf-8")).hexdigest()[:20]
        cid = f"hard-{digest}"
        for idx in indices:
            mapping[idx] = cid
    return mapping


def mixed_groups(
    records: Sequence[SmsRecord],
    component_map: Dict[int, str],
) -> Dict[str, List[SmsRecord]]:
    groups: Dict[str, List[SmsRecord]] = defaultdict(list)
    for idx, record in enumerate(records):
        groups[component_map[idx]].append(record)
    mixed = {}
    for gid, members in groups.items():
        labels = {member.label for member in members}
        if len(labels) > 1:
            mixed[gid] = members
    return mixed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare label conflict review pack.")
    parser.add_argument(
        "--train",
        type=Path,
        default=ROOT / "data" / "processed" / "train.jsonl",
    )
    parser.add_argument(
        "--validation",
        type=Path,
        default=ROOT / "data" / "processed" / "validation.jsonl",
    )
    parser.add_argument(
        "--quarantine",
        type=Path,
        default=ROOT / "data" / "interim" / "quarantine" / "train_quarantine_v1.jsonl",
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Train + validation only. Never read locked test for conflict packs.
    records: List[SmsRecord] = []
    for path in (args.train, args.validation, args.quarantine):
        if path.exists():
            records.extend(load_jsonl(path))
    if not records:
        print("No records available for conflict review.", file=sys.stderr)
        return 1

    by_id = {record.id: record for record in records}
    hard_map = hard_component_ids(records)
    hard_mixed = mixed_groups(records, hard_map)

    fp_groups: Dict[str, List[SmsRecord]] = defaultdict(list)
    for record in records:
        fp_groups[template_fingerprint(record.text)].append(record)
    fp_mixed = {
        f"fp-{fp}": members
        for fp, members in fp_groups.items()
        if len({member.label for member in members}) > 1
    }

    selected_ids: Set[str] = set(HARDCODED_REVIEW_IDS)
    review_groups: Dict[str, List[str]] = {}

    for gid, members in sorted(hard_mixed.items(), key=lambda item: item[0]):
        ids = sorted(member.id for member in members)
        review_groups[gid] = ids
        selected_ids.update(ids)

    for gid, members in sorted(fp_mixed.items(), key=lambda item: item[0]):
        ids = sorted(member.id for member in members)
        review_groups[gid] = ids
        selected_ids.update(ids)

    for record_id in sorted(HARDCODED_REVIEW_IDS):
        review_groups.setdefault(f"risk-{record_id}", [record_id])

    # Pool rows: one row per selected id present in train/validation/quarantine.
    pool_rows = []
    missing_hardcoded = sorted(rid for rid in HARDCODED_REVIEW_IDS if rid not in by_id)
    for record_id in sorted(selected_ids):
        record = by_id.get(record_id)
        if record is None:
            continue
        group_ids = [
            gid for gid, ids in review_groups.items() if record_id in ids
        ]
        pool_rows.append(
            {
                "review_group_id": "|".join(group_ids[:3]),
                "id": record.id,
                "text": record.text,
                "source_split": record.split,
                "source": record.source,
                "template_group": record.template_group,
                "sender_group": record.sender_group,
                "current_label": record.label,
            }
        )

    rng = random.Random(args.seed)
    order = list(range(len(pool_rows)))
    rng.shuffle(order)
    shuffled = [pool_rows[idx] for idx in order]

    blind_a = [
        {
            "review_group_id": row["review_group_id"],
            "id": row["id"],
            "text": row["text"],
            "label": "",
            "notes": "",
            "human_annotator_id": "",
        }
        for row in shuffled
    ]
    # Independent shuffle for B to reduce positional bias, still same membership.
    order_b = list(range(len(shuffled)))
    rng.shuffle(order_b)
    blind_b = [
        {
            "review_group_id": shuffled[idx]["review_group_id"],
            "id": shuffled[idx]["id"],
            "text": shuffled[idx]["text"],
            "label": "",
            "notes": "",
            "human_annotator_id": "",
        }
        for idx in order_b
    ]

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    pool_path = out / "conflict_pool.csv"
    a_path = out / "blind_annotator_A.csv"
    b_path = out / "blind_annotator_B.csv"
    write_csv(
        pool_path,
        shuffled,
        [
            "review_group_id",
            "id",
            "text",
            "source_split",
            "source",
            "template_group",
            "sender_group",
            "current_label",
        ],
    )
    write_csv(a_path, blind_a, BLIND_FIELDS)
    write_csv(b_path, blind_b, BLIND_FIELDS)

    guide_sha = sha256_file(GUIDE_PATH) if GUIDE_PATH.exists() else None
    manifest = {
        "version": "2.0.0",
        "status": "PENDING_DUAL_HUMAN_ANNOTATION",
        "claim_allowed": False,
        "model_scores_used": False,
        "test_text_exposed": False,
        "dual_human_evidence_complete": False,
        "seed": args.seed,
        "annotation_guide_sha256": guide_sha,
        "independence_attestation": {
            "required": True,
            "present": False,
            "note": (
                "Two real humans must independently annotate blind A/B sheets. "
                "Do not use AI-filled HUMAN_* labels."
            ),
        },
        "dual_human_evidence": {
            "independence_attestation": None,
            "started_at": None,
            "completed_at": None,
            "annotator_roster_internal_ref": None,
            "saw_model_suggestions": None,
        },
        "annotator_ids": {
            "A": "PENDING_ASSIGNMENT",
            "B": "PENDING_ASSIGNMENT",
        },
        "counts": {
            "pool_rows": len(shuffled),
            "hard_identity_conflict_components": len(hard_mixed),
            "fingerprint_conflict_groups": len(fp_mixed),
            "hardcoded_risk_ids": len(HARDCODED_REVIEW_IDS),
            "hardcoded_missing_from_train_val_quarantine": len(missing_hardcoded),
        },
        "hardcoded_missing_ids": missing_hardcoded,
        "files": {
            "conflict_pool": {
                "path": str(pool_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(pool_path),
            },
            "blind_annotator_A": {
                "path": str(a_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(a_path),
                "review_order_sha256": sha256_review_order(blind_a),
            },
            "blind_annotator_B": {
                "path": str(b_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(b_path),
                "review_order_sha256": sha256_review_order(blind_b),
            },
        },
        "blind_fields": BLIND_FIELDS,
        "forbidden_blind_fields": [
            "prior_label",
            "current_label",
            "source label",
            "model prediction",
            "confidence",
            "boundary_bucket",
            "annotator_a_label",
            "annotator_b_label",
        ],
        "note": (
            "Blind sheets intentionally omit prior/model labels. "
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
                "pool_rows": manifest["counts"]["pool_rows"],
                "hard_identity_conflict_components": manifest["counts"][
                    "hard_identity_conflict_components"
                ],
                "fingerprint_conflict_groups": manifest["counts"][
                    "fingerprint_conflict_groups"
                ],
                "output_dir": str(out.relative_to(ROOT)).replace("\\", "/"),
                "claim_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
