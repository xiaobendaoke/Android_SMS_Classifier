#!/usr/bin/env python3
"""Run approved independent xfyun blind relabeling on local-only packs."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from openai import OpenAI

from direct_xfyun_call import BASE_URL, api_key_from_demo

ROOT = Path(__file__).resolve().parent.parent
RUN = "xfyun_error_relabel_20260803_r1"
PACK = ROOT / "data/interim/annotation" / RUN
REPORT = ROOT / "reports/experiments" / RUN
DEMO = Path("/mnt/c/Users/woshinibaba/AppData/Local/Temp/opencode/xf_demo.py")
GUIDE = ROOT.parent / "docs/labeling-guide.md"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt(rows: list[dict[str, str]]) -> str:
    guide = GUIDE.read_text(encoding="utf-8")
    items = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    return f"""你是短信四分类标注员。仅依据正文判断主意图，严格遵循以下标注指南：\n{guide}\n\n对以下独立盲标包逐条标注。不要推断或讨论任何未提供的信息。每行输出一个 JSON 对象，字段只能为 review_key、id、label、notes；label 只能是 TRANSACTION、AD、HARASS、FRAUD、NEEDS_REVIEW；notes 必须非空，说明主意图、决定性证据和排除最易混淆类。不要输出 markdown 或额外文本。\n\n{items}\n"""


def run_one(client: OpenAI, name: str, model: str) -> dict[str, object]:
    input_path = PACK / f"{name}_blind.jsonl"
    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line]
    content = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt(rows)}]).choices[0].message.content
    if not content:
        raise ValueError(f"{name}: empty xfyun response")
    output_path = PACK / f"{name}_raw.txt"
    output_path.write_text(content + "\n", encoding="utf-8")
    return {"model": model, "input_sha256": sha(input_path), "output_sha256": sha(output_path), "candidate_count": len(rows)}


def main() -> int:
    if not PACK.exists():
        raise SystemExit(f"missing prepared pack: {PACK}")
    if (PACK / "pass_a_raw.txt").exists() or (PACK / "pass_b_raw.txt").exists():
        raise SystemExit("refusing to overwrite existing model output")
    REPORT.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key_from_demo(DEMO), base_url=BASE_URL, timeout=300.0, max_retries=0)
    manifest = {"run_id": RUN, "status": "PROVISIONAL_AUTOMATED_MULTI_PASS_PENDING_QA", "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "locked_test_read": False, "pass_a": run_one(client, "pass_a", "xopglm52"), "pass_b": run_one(client, "pass_b", "xopdeepseekv4flash")}
    (REPORT / "call_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": RUN, "pass_a": manifest["pass_a"]["candidate_count"], "pass_b": manifest["pass_b"]["candidate_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
