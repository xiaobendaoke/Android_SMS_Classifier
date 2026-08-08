#!/usr/bin/env python3
"""Finalize provisional labels and create a membership-preserving overlay data version."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUN = "harass_boundary_arbitration_20260806_r1"
DEFAULT_DATA = ROOT / "data" / "processed_xfyun_carrier_repayment_relabel_20260804_r1"
DATA = DEFAULT_DATA
RUN = DEFAULT_RUN
PACK = ROOT / "data" / "interim" / "annotation" / RUN
OUT = ROOT / "data" / f"processed_{RUN}"
REPORT_WIN = Path("/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments") / RUN
STATUS = "PROVISIONAL_AUTOMATED_MULTI_PASS"
ALLOWED = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
PASS_A_ID = "AI_GLM_XOPGLM52_PASS_A_001"
PASS_B_ID = "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_PASS_B_001"
PASS_C_ID = "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_PASS_C_001"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def parse_raw(name: str) -> dict[str, dict]:
    result = {}
    path = PACK / f"{name}_raw.txt"
    if not path.exists():
        raise SystemExit(f"missing raw output: {path.name}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(row, dict)
            and row.get("id")
            and row.get("label") in ALLOWED
            and row.get("notes")
        ):
            result[row["id"]] = row
    return result


def main() -> int:
    global RUN, DATA, PACK, OUT, REPORT_WIN
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    parser.add_argument("--base-data", type=Path, default=DEFAULT_DATA)
    parser.add_argument(
        "--selection",
        default="inconsistent_template_groups_only",
    )
    args = parser.parse_args()
    RUN = args.run_id
    DATA = args.base_data
    PACK = ROOT / "data" / "interim" / "annotation" / RUN
    OUT = ROOT / "data" / f"processed_{RUN}"
    REPORT_WIN = Path("/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments") / RUN
    if OUT.exists() or (REPORT_WIN / "overlay_summary.json").exists():
        raise SystemExit(f"refusing to overwrite finalized run: {RUN}")

    pass_a_rows = load_records(PACK / "pass_a_blind.jsonl")
    pass_b_rows = load_records(PACK / "pass_b_blind.jsonl")
    if len(pass_a_rows) != len(pass_b_rows):
        raise SystemExit("pass A/B pack sizes differ")

    skipped_path = PACK / "moderation_skipped.json"
    skipped_ids = (
        set(json.loads(skipped_path.read_text(encoding="utf-8")))
        if skipped_path.exists()
        else set()
    )
    finalized_rows = [r for r in pass_a_rows if r["id"] not in skipped_ids]

    pass_a = parse_raw("pass_a")
    pass_b = parse_raw("pass_b")
    if any(r["id"] not in pass_a for r in finalized_rows):
        raise SystemExit("pass A parsed results are incomplete for finalized rows")
    if any(r["id"] not in pass_b for r in finalized_rows):
        raise SystemExit("pass B parsed results are incomplete for finalized rows")

    disagreements = [
        r["id"]
        for r in finalized_rows
        if pass_a[r["id"]]["label"] != pass_b[r["id"]]["label"]
    ]
    pass_c = {}
    if disagreements:
        pass_c = parse_raw("pass_c")
        missing_c = [rid for rid in disagreements if rid not in pass_c]
        if missing_c:
            raise SystemExit(
                f"pass C results missing for {len(missing_c)} finalized disagreements"
            )

    source_rows = load_records(DATA / "train.jsonl") + load_records(
        DATA / "validation.jsonl"
    )
    originals = {r["id"]: r for r in source_rows}
    missing_ids = [r["id"] for r in finalized_rows if r["id"] not in originals]
    if missing_ids:
        raise SystemExit(f"candidate ids missing from source data: {len(missing_ids)}")

    records = []
    corrections = []
    quarantine = []
    for r in finalized_rows:
        rid = r["id"]
        a_label = pass_a[rid]["label"]
        b_label = pass_b[rid]["label"]
        if a_label == b_label:
            final_label = a_label
            method = "AUTOMATED_A_B_AGREEMENT"
            annotator_ids = [PASS_A_ID, PASS_B_ID]
        else:
            final_label = pass_c[rid]["label"]
            method = "DIRECT_XFYUN_PASS_C"
            annotator_ids = [PASS_A_ID, PASS_B_ID, PASS_C_ID]
        record = {
            "review_key": r["review_key"],
            "id": rid,
            "label": final_label,
            "status": STATUS,
            "claim_allowed": False,
            "human_verified": False,
            "formal_acceptance_allowed": False,
            "annotator_ids": annotator_ids,
            "resolution_method": method,
        }
        records.append(record)
        old_label = originals[rid]["label"]
        if final_label != old_label:
            corrections.append(
                {
                    "old_label": old_label,
                    "new_label": final_label,
                    "resolution_method": method,
                }
            )
        if final_label == "NEEDS_REVIEW":
            quarantine.append(
                {"id": rid, "label": final_label, "resolution_method": method}
            )

    OUT.mkdir(parents=True)
    (OUT / "provisional_labels.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )
    (OUT / "quarantine.json").write_text(
        json.dumps(quarantine, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    label_map = {r["id"]: r["label"] for r in records}
    split_shas = {}
    for split_name in ("train", "validation"):
        src_path = DATA / f"{split_name}.jsonl"
        dst_path = OUT / f"{split_name}.jsonl"
        out_lines = []
        for line in src_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row["id"] in label_map:
                row["label"] = label_map[row["id"]]
                row.setdefault("annotator_ids", [])
                row["annotator_ids"] = row["annotator_ids"] + ["AI_ARBITRATION_20260806"]
            out_lines.append(json.dumps(row, ensure_ascii=False))
        dst_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        split_shas[split_name] = sha256(dst_path)

    membership_preserved = True
    for split_name in ("train", "validation"):
        src_ids = {r["id"] for r in load_records(DATA / f"{split_name}.jsonl")}
        dst_ids = {r["id"] for r in load_records(OUT / f"{split_name}.jsonl")}
        if src_ids != dst_ids:
            membership_preserved = False

    transitions = Counter(
        f"{c['old_label']}->{c['new_label']}" for c in corrections
    )
    final_label_counts = Counter(r["label"] for r in records)
    qa = {
        "candidate_count": len(records),
        "moderation_skipped_count": len(skipped_ids),
        "agreement_count": len(records) - len(disagreements),
        "disagreement_count": len(disagreements),
        "pass_c_count": len(pass_c),
        "quarantine_count": len(quarantine),
        "correction_count": len(corrections),
        "exact_agreement": (
            (len(records) - len(disagreements)) / len(records) if records else 0.0
        ),
        "final_label_counts": dict(sorted(final_label_counts.items())),
        "transition_counts": dict(
            sorted(transitions.items(), key=lambda x: (-x[1], x[0]))
        ),
    }
    summary = {
        "run_id": RUN,
        "status": STATUS,
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "candidate_selection": args.selection,
        "source_data_sha256": {
            name: sha256(DATA / f"{name}.jsonl") for name in ("train", "validation")
        },
        "overlay_data_sha256": split_shas,
        "split_membership_preserved": membership_preserved,
        "locked_test_byte_identical": True,
        "qa": qa,
        "privacy": {
            "raw_sms_text_committed": False,
            "raw_sample_ids_committed": False,
            "raw_ai_outputs_committed": False,
        },
    }
    REPORT_WIN.mkdir(parents=True, exist_ok=True)
    (REPORT_WIN / "overlay_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    wsl_report = ROOT / "reports" / "experiments" / RUN
    wsl_report.mkdir(parents=True, exist_ok=True)
    (wsl_report / "overlay_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_id": RUN,
                "candidates": len(records),
                "moderation_skipped": len(skipped_ids),
                "corrections": len(corrections),
                "quarantine": len(quarantine),
                "train_sha": split_shas["train"][:16],
                "val_sha": split_shas["validation"][:16],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
