#!/usr/bin/env python3
"""Prepare a conflict-only local Pass C request for the carrier/repayment blind run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUN = "xfyun_carrier_repayment_relabel_20260804_r1"
PACK = ROOT / "data" / "interim" / "annotation" / RUN
GUIDE = ROOT.parent / "docs" / "labeling-guide.md"
LABELS = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(name: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for line in (PACK / f"{name}_raw.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        item_id, label, notes = item.get("id"), item.get("label"), item.get("notes")
        if not isinstance(item_id, str) or label not in LABELS or not isinstance(notes, str) or not notes.strip():
            raise ValueError(f"invalid {name} response row")
        if item_id in result:
            raise ValueError(f"duplicate {name} id: {item_id}")
        result[item_id] = {"label": label, "notes": notes.strip()}
    return result


def main() -> int:
    prompt_path = PACK / "pass_c_prompt.txt"
    input_path = PACK / "pass_c_input.jsonl"
    manifest_path = PACK / "pass_c_preparation_manifest.json"
    if any(path.exists() for path in (prompt_path, input_path, manifest_path, PACK / "pass_c_raw.txt")):
        raise SystemExit("refusing to overwrite existing Pass C material")

    source_rows = {
        item["id"]: item
        for line in (PACK / "pass_a_blind.jsonl").read_text(encoding="utf-8").splitlines()
        if line
        for item in [json.loads(line)]
    }
    a, b = parse("pass_a"), parse("pass_b")
    if set(a) != set(b) or set(a) != set(source_rows):
        raise ValueError("A/B/source membership mismatch")
    rows = [
        {
            "id": item_id,
            "text": source_rows[item_id]["text"],
            "a_label": a[item_id]["label"],
            "a_notes": a[item_id]["notes"],
            "b_label": b[item_id]["label"],
            "b_notes": b[item_id]["notes"],
        }
        for item_id in sorted(a)
        if a[item_id]["label"] != b[item_id]["label"]
    ]
    if not rows:
        raise ValueError("no A/B conflicts require Pass C")

    input_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    prompt = (
        "你是短信四分类仲裁员。严格依照以下标注指南：\n"
        + GUIDE.read_text(encoding="utf-8")
        + "\n\n以下仅为 A/B 冲突记录。逐条独立仲裁，可选择 TRANSACTION、AD、HARASS、FRAUD 或 NEEDS_REVIEW。"
        + "每行输出一个 JSON 对象，字段只能是 id、label、notes；notes 非空，必须说明主意图、决定性证据、拒绝 A 的理由和拒绝 B 的理由。"
        + "不要输出 markdown 或额外文本。\n\n"
        + "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    )
    prompt_path.write_text(prompt, encoding="utf-8")
    manifest_path.write_text(json.dumps({
        "run_id": RUN,
        "pass": "C",
        "annotator_id": "AI_DEEPSEEK_XOPDEEPSEEKV4FLASH_ADJUDICATOR_001",
        "model": "xopdeepseekv4flash",
        "transport": "direct_openai_sdk_xfyun_v2",
        "conflict_count": len(rows),
        "input_sha256": sha256(input_path),
        "prompt_sha256": sha256(prompt_path),
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": RUN, "pass_c_candidates": len(rows), "input_sha256": sha256(input_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
