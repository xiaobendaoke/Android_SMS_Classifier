#!/usr/bin/env python3
"""Run multi-pass AI arbitration for boundary rows via XFYun with moderation-safe retry."""
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


def call_chunk(
    client: OpenAI,
    model_name: str,
    rows: list[dict],
    guide_text: str,
    prompt_builder,
) -> str:
    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt_builder(rows, guide_text)}],
        timeout=300.0,
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError("empty xfyun response")
    return content


def parse_chunk_content(content: str, expected_ids: set[str], results: dict) -> None:
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


def attempt(
    client: OpenAI,
    model_name: str,
    rows: list[dict],
    guide_text: str,
    prompt_builder,
    expected_ids: set[str],
    results: dict,
    raw_chunks: list[str],
    skipped: list[str],
    pass_name: str,
    size: int,
) -> None:
    if not rows:
        return
    if len(rows) > size:
        mid = len(rows) // 2
        attempt(
            client,
            model_name,
            rows[:mid],
            guide_text,
            prompt_builder,
            expected_ids,
            results,
            raw_chunks,
            skipped,
            pass_name,
            size,
        )
        attempt(
            client,
            model_name,
            rows[mid:],
            guide_text,
            prompt_builder,
            expected_ids,
            results,
            raw_chunks,
            skipped,
            pass_name,
            size,
        )
        return
    try:
        content = call_chunk(client, model_name, rows, guide_text, prompt_builder)
        raw_chunks.append(content)
        parse_chunk_content(content, expected_ids, results)
    except Exception:
        if len(rows) == 1:
            skipped.append(rows[0]["id"])
            print(f"{pass_name}: skipped 1 row after moderation/error retries")
        else:
            mid = len(rows) // 2
            attempt(
                client,
                model_name,
                rows[:mid],
                guide_text,
                prompt_builder,
                expected_ids,
                results,
                raw_chunks,
                skipped,
                pass_name,
                max(1, size // 2),
            )
            attempt(
                client,
                model_name,
                rows[mid:],
                guide_text,
                prompt_builder,
                expected_ids,
                results,
                raw_chunks,
                skipped,
                pass_name,
                max(1, size // 2),
            )


def parse_raw_file(path: Path, expected_ids: set[str]) -> dict[str, dict]:
    results: dict[str, dict] = {}
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
            and row.get("id") in expected_ids
            and row.get("label") in ALLOWED
            and row.get("notes")
        ):
            results[row["id"]] = row
    return results


def run_pass(
    client: OpenAI,
    model_name: str,
    rows: list[dict],
    guide_text: str,
    pass_name: str,
    prompt_builder=build_prompt,
) -> tuple[dict[str, dict], list[str]]:
    raw_path = PACK / f"{pass_name}_raw.txt"
    skipped_path = PACK / f"{pass_name}_skipped.json"
    if raw_path.exists():
        skipped = (
            json.loads(skipped_path.read_text(encoding="utf-8"))
            if skipped_path.exists()
            else []
        )
        results = parse_raw_file(raw_path, {r["id"] for r in rows})
        missing = [
            rid for rid in {r["id"] for r in rows} if rid not in results
        ]
        if missing:
            skipped = sorted(set(skipped) | set(missing))
            skipped_path.write_text(
                json.dumps(skipped, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                f"{pass_name}: {len(missing)} rows missing parsed output, "
                "marked skipped"
            )
        print(
            f"{pass_name}: reused existing raw output "
            f"({len(results)} parsed, {len(skipped)} skipped)"
        )
        return results, skipped

    results: dict[str, dict] = {}
    skipped: list[str] = []
    raw_chunks: list[str] = []
    expected_ids = {r["id"] for r in rows}
    total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    for index in range(0, len(rows), BATCH_SIZE):
        batch = rows[index : index + BATCH_SIZE]
        attempt(
            client,
            model_name,
            batch,
            guide_text,
            prompt_builder,
            expected_ids,
            results,
            raw_chunks,
            skipped,
            pass_name,
            BATCH_SIZE,
        )
        print(
            f"{pass_name} batch {index // BATCH_SIZE + 1}/{total_batches}: "
            f"{len(results)}/{len(rows)} parsed, {len(skipped)} skipped"
        )
    raw_path.write_text("\n".join(raw_chunks) + "\n", encoding="utf-8")
    if skipped:
        skipped_path.write_text(
            json.dumps(sorted(skipped), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    missing = [rid for rid in expected_ids if rid not in results]
    if missing:
        skipped = sorted(set(skipped) | set(missing))
        skipped_path.write_text(
            json.dumps(skipped, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"{pass_name}: {len(missing)} rows missing parsed output, "
            "marked skipped"
        )
    return results, skipped


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
    pass_a, a_skipped = run_pass(
        client, "xopglm52", pass_a_rows, guide_text, "pass_a"
    )
    print("Running pass B (xopdeepseekv4flash)...")
    pass_b, b_skipped = run_pass(
        client, "xopdeepseekv4flash", pass_b_rows, guide_text, "pass_b"
    )

    skipped_ids = sorted(set(a_skipped) | set(b_skipped))
    valid_ids = [r["id"] for r in pass_a_rows if r["id"] not in set(skipped_ids)]
    disagreements = [
        r
        for r in pass_a_rows
        if r["id"] in pass_a
        and r["id"] in pass_b
        and pass_a[r["id"]]["label"] != pass_b[r["id"]]["label"]
    ]
    agreements = len(valid_ids) - len(disagreements)
    print(
        f"A/B agreement: {agreements}/{len(valid_ids)}, "
        f"disagreements: {len(disagreements)}, skipped: {len(skipped_ids)}"
    )

    pass_c: dict[str, dict] = {}
    c_skipped: list[str] = []
    if disagreements:
        print("Running pass C (adjudication)...")
        (PACK / "pass_c_input.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in disagreements),
            encoding="utf-8",
        )
        pass_c, c_skipped = run_pass(
            client,
            "xopdeepseekv4flash",
            disagreements,
            guide_text,
            "pass_c",
            prompt_builder=build_pass_c_prompt,
        )
    skipped_ids = sorted(set(skipped_ids) | set(c_skipped))
    if skipped_ids:
        (PACK / "moderation_skipped.json").write_text(
            json.dumps(skipped_ids, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
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
        "moderation_skipped_count": len(skipped_ids),
        "pass_a": {
            "model": "xopglm52",
            "input_sha256": sha256(PACK / "pass_a_blind.jsonl"),
            "output_sha256": sha256(PACK / "pass_a_raw.txt"),
            "parsed_count": len(pass_a),
            "skipped_count": len(a_skipped),
        },
        "pass_b": {
            "model": "xopdeepseekv4flash",
            "input_sha256": sha256(PACK / "pass_b_blind.jsonl"),
            "output_sha256": sha256(PACK / "pass_b_raw.txt"),
            "parsed_count": len(pass_b),
            "skipped_count": len(b_skipped),
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
            "skipped_count": len(c_skipped),
        },
        "agreement_count": agreements,
        "disagreement_count": len(disagreements),
        "valid_count": len(valid_ids),
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
                "valid_count": len(valid_ids),
                "agreement_count": agreements,
                "disagreement_count": len(disagreements),
                "pass_c_parsed": len(pass_c),
                "moderation_skipped_count": len(skipped_ids),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
