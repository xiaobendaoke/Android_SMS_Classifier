#!/usr/bin/env python3
"""Prepare local prompt files for the approved-only carrier/repayment blind run."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = "xfyun_carrier_repayment_relabel_20260804_r1"
PACK = ROOT / "data/interim/annotation" / RUN
GUIDE = ROOT.parent / "docs/labeling-guide.md"


def main() -> int:
    if not PACK.exists():
        raise SystemExit(f"missing prepared pack: {PACK}")
    guide = GUIDE.read_text(encoding="utf-8")
    for name in ("pass_a", "pass_b"):
        rows = [json.loads(line) for line in (PACK / f"{name}_blind.jsonl").read_text(encoding="utf-8").splitlines() if line]
        prompt = (
            "你是短信四分类标注员。仅依据正文判断主意图，严格遵循以下标注指南：\n"
            + guide
            + "\n\n对以下独立盲标包逐条标注。每行输出 JSON，字段只能是 review_key、id、label、notes；"
            + "label 只能是 TRANSACTION、AD、HARASS、FRAUD、NEEDS_REVIEW；notes 必须非空，说明主意图、决定性证据和排除最易混淆类。"
            + "不要输出 markdown 或额外文本。\n\n"
            + "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        )
        (PACK / f"{name}_prompt.txt").write_text(prompt, encoding="utf-8")
    print(json.dumps({"run_id": RUN, "status": "LOCAL_PROMPTS_READY_PENDING_EXTERNAL_APPROVAL"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
