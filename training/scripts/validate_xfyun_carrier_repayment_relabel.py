#!/usr/bin/env python3
"""Validate the local-only A/B outputs for the carrier/repayment blind relabel run."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUN = "xfyun_carrier_repayment_relabel_20260804_r1"
PACK = ROOT / "data" / "interim" / "annotation" / RUN
REPORT = Path(os.environ.get("SAFE_REPORT_ROOT", ROOT / "reports" / "experiments" / RUN))
LABELS = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
BLIND_FIELDS = {"review_key", "id", "text"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_blind(name: str) -> tuple[dict[str, str], dict[str, object]]:
    rows = [json.loads(line) for line in (PACK / f"{name}_blind.jsonl").read_text(encoding="utf-8").splitlines() if line]
    ids = [row.get("id") for row in rows]
    keys = [row.get("review_key") for row in rows]
    fields_ok = all(set(row) == BLIND_FIELDS for row in rows)
    valid = all(isinstance(item, str) and item for item in ids + keys)
    return (
        {row["id"]: row["review_key"] for row in rows if isinstance(row.get("id"), str)},
        {
            "count": len(rows),
            "unique_ids": len(set(ids)) == len(ids),
            "unique_review_keys": len(set(keys)) == len(keys),
            "exact_blind_fields": fields_ok,
            "required_fields_nonempty": valid,
            "sha256": sha256(PACK / f"{name}_blind.jsonl"),
        },
    )


def parse_output(name: str, expected: dict[str, str]) -> tuple[dict[str, dict[str, str]], dict[str, object]]:
    path = PACK / f"{name}_raw.txt"
    rows: dict[str, dict[str, str]] = {}
    malformed = 0
    duplicate_ids = 0
    format_wrapper_lines = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower() in {"```", "```json"}:
            format_wrapper_lines += 1
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        item_id, label, notes = item.get("id"), item.get("label"), item.get("notes")
        if item_id not in expected or label not in LABELS or not isinstance(notes, str) or not notes.strip():
            malformed += 1
        elif item_id in rows:
            duplicate_ids += 1
        else:
            rows[item_id] = {"label": label, "notes": notes.strip()}
    return rows, {
        "valid": len(rows),
        "missing": len(set(expected) - set(rows)),
        "malformed": malformed,
        "duplicate_ids": duplicate_ids,
        "format_wrapper_lines_ignored": format_wrapper_lines,
        "label_counts": dict(Counter(row["label"] for row in rows.values())),
        "raw_output_sha256": sha256(path),
    }


def main() -> int:
    a_expected, a_blind = load_blind("pass_a")
    b_expected, b_blind = load_blind("pass_b")
    a_rows, a_output = parse_output("pass_a", a_expected)
    b_rows, b_output = parse_output("pass_b", b_expected)
    common = sorted(set(a_rows) & set(b_rows))
    conflicts = [item_id for item_id in common if a_rows[item_id]["label"] != b_rows[item_id]["label"]]
    c_expected = {item_id: "" for item_id in conflicts}
    c_rows, c_output = parse_output("pass_c", c_expected)
    same_notes = sum(a_rows[item_id]["notes"] == b_rows[item_id]["notes"] for item_id in common)
    complete = all(
        (
            a_blind["unique_ids"], a_blind["unique_review_keys"], a_blind["exact_blind_fields"], a_blind["required_fields_nonempty"],
            b_blind["unique_ids"], b_blind["unique_review_keys"], b_blind["exact_blind_fields"], b_blind["required_fields_nonempty"],
            set(a_expected) == set(b_expected),
            a_output["valid"] == len(a_expected), b_output["valid"] == len(b_expected),
            a_output["malformed"] == 0, b_output["malformed"] == 0,
            a_output["duplicate_ids"] == 0, b_output["duplicate_ids"] == 0,
            c_output["valid"] == len(conflicts), c_output["malformed"] == 0, c_output["duplicate_ids"] == 0,
            same_notes < len(common),
        )
    )
    payload = {
        "run_id": RUN,
        "status": "PROVISIONAL_AUTOMATED_MULTI_PASS" if complete else "PROVISIONAL_AUTOMATED_MULTI_PASS_QA_FAILED",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "blind_input": {"pass_a": a_blind, "pass_b": b_blind, "same_id_membership": set(a_expected) == set(b_expected)},
        "pass_a": a_output,
        "pass_b": b_output,
        "pass_c": c_output,
        "independence": {"common_valid": len(common), "identical_notes_count": same_notes, "all_notes_identical": same_notes == len(common) and bool(common)},
        "agreement": {"conflict_count": len(conflicts), "conflict_ids": conflicts, "exact_agreement": (len(common) - len(conflicts)) / len(common) if common else 0.0},
        "next_action": "finalize_local_overlay" if complete else "repair_or_rerun_local_qa",
    }
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "qa_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
