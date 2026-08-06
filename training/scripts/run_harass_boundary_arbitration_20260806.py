#!/usr/bin/env python3
"""Run multi-pass AI arbitration for inconsistent template groups via XFYun."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from openai import OpenAI

from direct_xfyun_call import BASE_URL, api_key_from_demo

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUN = "harass_boundary_arbitration_20260806_r1"
RUN = DEFAULT_RUN
PACK = ROOT / "data" / "interim" / "annotation" / RUN
REPORT_WIN = Path("/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments") / RUN
GUIDE = ROOT.parent / "docs" / "labeling-guide.md"
DEMO = Path("/mnt/c/Users/woshinibaba/AppData/Local/Temp/opencode/xf_demo.py")
BATCH_SIZE = 50
ALLOWED = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (PACK / f"{name}_blind.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]


def build_prompt(rows: list[dict], guide_text: str) -> str:
    items = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    return (
        "你是短信四分类标注员。仅依据正文判断主意图，严格遵循以下标注指南：\n"
        f"{guide_text}\n"
        "对以下独立盲标包逐条标注。不要推断或讨论任何未提供的信息。"
        "每行输出一个 JSON 对象，字段只能为 review_key、id、label、notes；"
        "label 只能是 TRANSACTION、AD、HARASS、FRAUD、NEEDS_REVIEW；"
        "notes 必须非空，说明主意图、决定性证据和排除最易混淆类。"
        "不要输出 markdown 或额外文本。\n\n"
        f"{items}\n"
    )


def build_pass_c_prompt(rows: list[dict], guide_text: str) -> str:
    items = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    return (
        "你是短信四分类仲裁员。两位标注员对同一短信给出了不同标签。"
        "请根据正文判断正确标签。\n标注指南：\n"
        f"{guide_text}\n"
        "对以下有争议的短信逐条输出最终标签。每行输出一个 JSON 对象，"
        "字段只能为 review_key、id、label、notes；"
        "label 只能是 TRANSACTION、AD、HARASS、FRAUD、NEEDS_REVIEW；"
        "notes 必须非空。不要输出 markdown 或额外文本。\n\n"
        f"{items}\n"
    )


def run_pass(
    client: OpenAI,
    model_name: str,
    rows: list[dict],
    guide_text: str,
    pass_name: str,
    prompt_builder=build_prompt,
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    raw_chunks = []
    expected_ids = {r["id"] for r in rows}
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    for index in range(0, len(rows), BATCH_SIZE):
        batch = rows[index : index + BATCH_SIZE]
        resp = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt_builder(batch, guide_text)}],
            timeout=300.0,
        )
        content = resp.choices[0].message.content
        if not content:
            raise ValueError(f"{pass_name} batch {index}: empty response")
        raw_chunks.append(content)
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(row, dict)
                and row.get("id") in expected_ids
                and row.get("label") in ALLOWED
                and row.get("notes")
            ):
                results[row["id"]] = row
        print(
            f"{pass_name} batch {index // BATCH_SIZE + 1}/{total_batches}: "
            f"{len(results)}/{len(rows)} parsed"
        )
    out_path = PACK / f"{pass_name}_raw.txt"
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite {out_path.name}")
    out_path.write_text("\n".join(raw_chunks) + "\n", encoding="utf-8")
    if len(results) != len(rows):
        missing = len(rows) - len(results)
        raise SystemExit(f"{pass_name}: {missing} rows missing valid output")
    return results


def main() -> int:
    global RUN, PACK, REPORT_WIN
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_RUN)
    args = parser.parse_args()
    RUN = args.run_id
    PACK = ROOT / "data" / "interim" / "annotation" / RUN
    REPORT_WIN = Path("/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments") / RUN
    if not PACK.exists():
        raise SystemExit(f"missing prepared pack: {PACK}")
    guide_text = GUIDE.read_text(encoding="utf-8")
    pass_a_rows = load_rows("pass_a")
    pass_b_rows = load_rows("pass_b")
    if len(pass_a_rows) != len(pass_b_rows):
        raise SystemExit("pass A/B pack sizes differ")
    client = OpenAI(
        api_key=api_key_from_demo(DEMO),
        base_url=BASE_URL,
        timeout=300.0,
        max_retries=0,
    )
    print("Running pass A (xopglm52)...")
    pass_a = run_pass(client, "xopglm52", pass_a_rows, guide_text, "pass_a")
    print("Running pass B (xopdeepseekv4flash)...")
    pass_b = run_pass(client, "xopdeepseekv4flash", pass_b_rows, guide_text, "pass_b")

    disagreements = []
    for r in pass_a_rows:
        a_label = pass_a[r["id"]]["label"]
        b_label = pass_b[r["id"]]["label"]
        if a_label != b_label:
            disagreements.append(
                {
                    "review_key": r["review_key"],
                    "id": r["id"],
                    "text": r["text"],
                    "pass_a_label": a_label,
                    "pass_b_label": b_label,
                }
            )
    print(
        f"A/B agreement: {len(pass_a_rows) - len(disagreements)}/{len(pass_a_rows)}, "
        f"disagreements: {len(disagreements)}"
    )
    pass_c: dict[str, dict] = {}
    if disagreements:
        print("Running pass C (adjudication)...")
        (PACK / "pass_c_input.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in disagreements),
            encoding="utf-8",
        )
        pass_c = run_pass(
            client,
            "xopdeepseekv4flash",
            disagreements,
            guide_text,
            "pass_c",
            prompt_builder=build_pass_c_prompt,
        )
    REPORT_WIN.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": RUN,
        "status": "PROVISIONAL_AUTOMATED_MULTI_PASS_PENDING_FINALIZE",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "candidate_count": len(pass_a_rows),
        "pass_a": {
            "model": "xopglm52",
            "input_sha256": sha256(PACK / "pass_a_blind.jsonl"),
            "output_sha256": sha256(PACK / "pass_a_raw.txt"),
            "parsed_count": len(pass_a),
        },
        "pass_b": {
            "model": "xopdeepseekv4flash",
            "input_sha256": sha256(PACK / "pass_b_blind.jsonl"),
            "output_sha256": sha256(PACK / "pass_b_raw.txt"),
            "parsed_count": len(pass_b),
        },
        "pass_c": {
            "model": "xopdeepseekv4flash",
            "input_sha256": (
                sha256(PACK / "pass_c_input.jsonl") if pass_c else None
            ),
            "output_sha256": (
                sha256(PACK / "pass_c_raw.txt") if pass_c else None
            ),
            "parsed_count": len(pass_c),
        },
        "agreement_count": len(pass_a_rows) - len(disagreements),
        "disagreement_count": len(disagreements),
        "privacy": {
            "raw_sms_text_committed": False,
            "raw_sample_ids_committed": False,
            "raw_ai_outputs_committed": False,
        },
    }
    (REPORT_WIN / "call_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_id": RUN,
                "candidate_count": len(pass_a_rows),
                "agreement_count": manifest["agreement_count"],
                "disagreement_count": manifest["disagreement_count"],
                "pass_c_parsed": len(pass_c),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
