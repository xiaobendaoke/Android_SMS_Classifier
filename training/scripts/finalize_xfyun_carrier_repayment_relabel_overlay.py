#!/usr/bin/env python3
"""Finalize a local-only, validation-only provisional overlay from xfyun A/B/C QA."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
RUN = "xfyun_carrier_repayment_relabel_20260804_r1"
PACK = ROOT / "data" / "interim" / "annotation" / RUN
SOURCE = ROOT / "data" / "processed_xfyun_error_relabel_20260803_r1"
OUTPUT = ROOT / "data" / f"processed_{RUN}"
OVERLAY = PACK / f"automated_label_corrections_{RUN}.json"
QUARANTINE = ROOT / "data" / "interim" / "quarantine" / f"{RUN}_needs_review.json"
REPORT = Path(os.environ.get("SAFE_REPORT_ROOT", ROOT / "reports" / "experiments" / RUN))
LABELS = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
ANNOTATORS = [
    "AI_GLM_XOPGLM52_PASS_A_001",
    "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_PASS_B_001",
]
ADJUDICATOR = "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_ADJUDICATOR_001"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_jsonl(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().lower() in {"```", "```json"}:
            continue
        row = json.loads(line)
        item_id = row.get("id")
        if not isinstance(item_id, str) or item_id in result:
            raise ValueError(f"invalid or duplicate id in {path.name}")
        result[item_id] = row
    return result


def main() -> int:
    if OUTPUT.exists() or OVERLAY.exists() or QUARANTINE.exists():
        raise SystemExit("refusing to overwrite finalized provisional overlay")
    qa = json.loads((REPORT / "qa_summary.json").read_text(encoding="utf-8"))
    if qa.get("status") != "PROVISIONAL_AUTOMATED_MULTI_PASS":
        raise ValueError("A/B/C QA must pass before finalization")

    originals = parse_jsonl(PACK / "pass_a_blind.jsonl")
    a, b, c = (parse_jsonl(PACK / f"pass_{name}_raw.txt") for name in ("a", "b", "c"))
    conflicts = {item_id for item_id in originals if a[item_id]["label"] != b[item_id]["label"]}
    if set(c) != conflicts:
        raise ValueError("Pass C must cover exactly the A/B conflict IDs")
    if set(a) != set(originals) or set(b) != set(originals):
        raise ValueError("A/B membership mismatch")

    source_validation = parse_jsonl(SOURCE / "validation.jsonl")
    source_train = parse_jsonl(SOURCE / "train.jsonl")
    if not set(originals).issubset(source_validation) or set(originals) & set(source_train):
        raise ValueError("candidate membership is not validation-only")
    final = {item_id: (c[item_id] if item_id in conflicts else a[item_id]) for item_id in originals}
    if any(row.get("label") not in LABELS for row in final.values()):
        raise ValueError("invalid final label")

    corrections, needs_review = [], []
    transition_counts: Counter[str] = Counter()
    for item_id, result in final.items():
        original = source_validation[item_id]
        final_label = result["label"]
        transition_counts[f"{original['label']}->{final_label}"] += 1
        base = {
            "id": item_id,
            "final_label": final_label,
            "text_sha256": hashlib.sha256(originals[item_id]["text"].encode("utf-8")).hexdigest(),
            "annotator_ids": ANNOTATORS + ([ADJUDICATOR] if item_id in conflicts else []),
        }
        if final_label == "NEEDS_REVIEW":
            needs_review.append(base)
        elif final_label != original["label"]:
            corrections.append(base)

    payload = {
        "run_id": RUN,
        "status": "PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "corrections": corrections,
    }
    OVERLAY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    QUARANTINE.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE.write_text(json.dumps({
        "run_id": RUN,
        "status": "PROVISIONAL_AUTOMATED_MULTI_PASS",
        "records": needs_review,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    command = [
        sys.executable, str(ROOT / "scripts" / "apply_automated_terra_overlay.py"),
        "--overlay", str(OVERLAY), "--source", str(SOURCE), "--output", str(OUTPUT),
        "--quarantine", str(ROOT / "data" / "interim" / "quarantine" / f"{RUN}_train.jsonl"),
    ]
    completed = subprocess.run(command, cwd=REPO, env={**os.environ, "PYTHONPATH": str(ROOT)}, check=False)
    manifest = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8")) if completed.returncode == 0 else {}
    safe_manifest = {
        "run_id": RUN,
        "status": "PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "annotators": ANNOTATORS + [ADJUDICATOR],
        "transport": "direct_openai_sdk_xfyun_v2",
        "input_sha256": {"pass_a": qa["pass_a"]["raw_output_sha256"], "pass_b": qa["pass_b"]["raw_output_sha256"], "pass_c": qa["pass_c"]["raw_output_sha256"]},
        "agreement": qa["agreement"],
        "qa_summary_sha256": sha256(REPORT / "qa_summary.json"),
        "correction_count": len(corrections),
        "needs_review_count": len(needs_review),
        "transition_counts": dict(transition_counts),
    }
    safe_report = {
        **safe_manifest,
        "overlay_sha256": sha256(OVERLAY),
        "returncode": completed.returncode,
        "overlay_manifest": manifest,
        "template_audit": {"status": "NO_RAW_TEMPLATE_CONTENT_EXPORTED", "candidate_count": len(originals)},
    }
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "automated_annotation_manifest.json").write_text(json.dumps(safe_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT / "automated_annotation_report.json").write_text(json.dumps(safe_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT / "overlay_summary.json").write_text(json.dumps(safe_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(safe_report, ensure_ascii=False))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
