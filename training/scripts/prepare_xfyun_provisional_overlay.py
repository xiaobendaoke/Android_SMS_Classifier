#!/usr/bin/env python3
"""Build a schema-compatible exploratory overlay from direct-xfyun annotations."""
from __future__ import annotations

import json
from pathlib import Path


TRAINING = Path(__file__).resolve().parent.parent
RUN_ID = "ai_annotation_20260802_r1"
DIRECT = TRAINING / "data/interim/annotation/automated_runs" / RUN_ID / "direct_xfyun_pass_c_20260803"
OUTPUT = TRAINING / "data/interim/annotation" / f"xfyun_overlay_{RUN_ID}.json"


def main() -> int:
    source = json.loads((DIRECT / f"automated_label_corrections_{RUN_ID}.json").read_text(encoding="utf-8"))
    corrections = []
    for item in source["corrections"]:
        corrections.append({"id": item["id"], "final_label": item["label"], "text_sha256": item["text_sha256"], "annotator_ids": ["AI_GLM_XOPGLM52_PASS_A_001", "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_PASS_B_001"] + (["AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_ADJUDICATOR_001"] if item["resolution_method"] == "DIRECT_XFYUN_PASS_C" else [])})
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"run_id": RUN_ID, "status": "PROVISIONAL_AUTOMATED_MULTI_PASS", "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "transport": "direct_openai_sdk_xfyun_v2", "corrections": corrections}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "corrections": len(corrections), "claim_allowed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
