#!/usr/bin/env python3
"""Run approved Pass C adjudication for local A/B blind-label conflicts."""
from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from direct_xfyun_call import BASE_URL, api_key_from_demo

ROOT = Path(__file__).resolve().parent.parent
RUN = "xfyun_error_relabel_20260803_r1"
PACK = ROOT / "data/interim/annotation" / RUN
REPORT = ROOT / "reports/experiments" / RUN
DEMO = Path("/mnt/c/Users/woshinibaba/AppData/Local/Temp/opencode/xf_demo.py")
GUIDE = ROOT.parent / "docs/labeling-guide.md"


def parse(name: str) -> dict[str, dict[str, str]]:
    result = {}
    for line in (PACK / f"{name}_raw.txt").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("{"):
            row = json.loads(line)
            result[row["id"]] = row
    return result


def main() -> int:
    output = PACK / "pass_c_raw.txt"
    if output.exists():
        raise SystemExit("refusing to overwrite Pass C output")
    originals = {json.loads(line)["id"]: json.loads(line) for line in (PACK / "pass_a_blind.jsonl").read_text(encoding="utf-8").splitlines() if line}
    a, b = parse("pass_a"), parse("pass_b")
    rows = [{"id": item_id, "text": originals[item_id]["text"], "a_label": a[item_id]["label"], "a_notes": a[item_id]["notes"], "b_label": b[item_id]["label"], "b_notes": b[item_id]["notes"]} for item_id in sorted(set(a) & set(b)) if a[item_id]["label"] != b[item_id]["label"]]
    (PACK / "pass_c_input.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    prompt = (
        "你是短信四分类仲裁员。严格依照以下标注指南：\n"
        + GUIDE.read_text(encoding="utf-8")
        + "\n\n以下仅为 A/B 冲突记录。逐条独立仲裁，可选择 TRANSACTION、AD、HARASS、FRAUD 或 NEEDS_REVIEW。"
        + "每行输出一个 JSON 对象，字段只能是 id、label、notes；notes 非空，必须说明主意图、决定性证据、拒绝 A 的理由和拒绝 B 的理由。"
        + "不要输出 markdown 或额外文本。\n\n"
        + "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    )
    client = OpenAI(api_key=api_key_from_demo(DEMO), base_url=BASE_URL, timeout=300.0, max_retries=0)
    content = client.chat.completions.create(model="xopdeepseekv4flash", messages=[{"role": "user", "content": prompt}]).choices[0].message.content
    if not content:
        raise ValueError("empty Pass C response")
    output.write_text(content + "\n", encoding="utf-8")
    print(json.dumps({"run_id": RUN, "pass_c_candidates": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
