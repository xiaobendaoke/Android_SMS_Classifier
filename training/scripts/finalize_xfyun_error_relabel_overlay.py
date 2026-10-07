#!/usr/bin/env python3
"""Create a membership-preserving provisional overlay from local xfyun QA."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
RUN = "xfyun_error_relabel_20260803_r1"
PACK = ROOT / "data/interim/annotation" / RUN
SOURCE = ROOT / "data/processed_xfyun_ai_annotation_20260802_r1"
OVERLAY = PACK / f"automated_label_corrections_{RUN}.json"
OUTPUT = ROOT / f"data/processed_{RUN}"
QUARANTINE = ROOT / "data/interim/quarantine" / f"{RUN}_needs_review.json"
REPORT = ROOT / "reports/experiments" / RUN


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(path: Path) -> dict[str, dict]:
    return {row["id"]: row for line in path.read_text(encoding="utf-8").splitlines() if line and (row := json.loads(line))}


def main() -> int:
    if OUTPUT.exists() or OVERLAY.exists():
        raise SystemExit("refusing to overwrite finalized overlay")
    originals = parse(PACK / "pass_a_blind.jsonl")
    a, b = parse(PACK / "pass_a_raw.txt"), parse(PACK / "pass_b_raw.txt")
    c = parse(PACK / "pass_c_raw.txt")
    final = {item: (c[item] if a[item]["label"] != b[item]["label"] else a[item]) for item in originals}
    corrections, needs_review = [], []
    for item, result in final.items():
        record = {"id": item, "final_label": result["label"], "text_sha256": hashlib.sha256(originals[item]["text"].encode("utf-8")).hexdigest(), "annotator_ids": ["AI_GLM_XOPGLM52_PASS_A_001", "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_PASS_B_001"] + (["AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_ADJUDICATOR_001"] if item in c else [])}
        if result["label"] == "NEEDS_REVIEW":
            needs_review.append(record)
        elif result["label"] == "AD":
            corrections.append(record)
    payload = {"run_id": RUN, "status": "PROVISIONAL_AUTOMATED_MULTI_PASS", "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "corrections": corrections}
    OVERLAY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    QUARANTINE.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE.write_text(json.dumps({"status": "PROVISIONAL_AUTOMATED_MULTI_PASS", "records": needs_review}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "scripts/apply_automated_terra_overlay.py"), "--overlay", str(OVERLAY), "--source", str(SOURCE), "--output", str(OUTPUT), "--quarantine", str(ROOT / "data/interim/quarantine" / f"{RUN}_train.jsonl")]
    completed = subprocess.run(cmd, cwd=REPO, env={**os.environ, "PYTHONPATH": str(ROOT)})
    manifest = json.loads((OUTPUT / "manifest.json").read_text(encoding="utf-8")) if completed.returncode == 0 else {}
    REPORT.mkdir(parents=True, exist_ok=True)
    safe = {"run_id": RUN, "status": payload["status"], "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "locked_test_read": False, "applied_ad_corrections": len(corrections), "needs_review_held_out_of_validation": len(needs_review), "overlay_sha256": sha(OVERLAY), "returncode": completed.returncode, "overlay_manifest": manifest}
    (REPORT / "overlay_summary.json").write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(safe, ensure_ascii=False))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
