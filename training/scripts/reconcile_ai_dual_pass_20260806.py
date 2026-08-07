#!/usr/bin/env python3
"""Reconcile NVIDIA dual-pass A/B/C outputs into a user review package."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
GUIDE = REPO / "docs" / "labeling-guide.md"

RUN_ID_DEFAULT = "ai_dual_pass_20260806_r1"
PASS_A_MODEL = "nvidia/stepfun-ai/step-3.7-flash"
PASS_B_MODEL = "moreai/MiniMax-M3"
PASS_C_MODEL = "moreai/MiniMax-M3"
PASS_A_ID = "AUTO_STEP3_7FLASH_PASS_A_001"
PASS_B_ID = "AUTO_MOREAI_MINIMAXM3_PASS_B_001"
PASS_C_ID = "AUTO_MOREAI_MINIMAXM3_ADJUDICATOR_001"
ALLOWED = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
LOW_CONFIDENCE_THRESHOLD = 0.60

GUIDE_CONDENSED = """四分类唯一判断顺序（逐条短信只判一次主意图）：
1) 是否在骗（冒充/假奖励/索要验证码或转账/钓鱼链接） -> FRAUD
2) 是否业务结果告知（账户/订单/认证/物流/运营商/还款） -> TRANSACTION
3) 是否正规商家促销（办卡/优惠/会员/宽带） -> AD
4) 是否催收/灰产/成人/赌博/强行推销（不靠骗转账） -> HARASS
5) 其他或不确定 -> NEEDS_REVIEW
注意：看到银行/验证码/链接不等于事务或诈骗；按正文主意图判断；每条只选一个标签；吃不准就 NEEDS_REVIEW。"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def write_csv(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def parse_output(path: Path) -> List[dict]:
    """Tolerant JSONL parser: accepts JSON objects, arrays, and fenced blocks."""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"```(?:json)?", "", text)
    objects: List[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        value = None
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", line, flags=re.S)
            if match:
                try:
                    value = json.loads(match.group(0))
                except json.JSONDecodeError:
                    value = None
        if isinstance(value, list):
            objects.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            objects.append(value)
    return objects


def normalize_object(obj: dict, expected: Dict[Tuple[str, str], dict]) -> Optional[dict]:
    review_id = str(obj.get("review_id", "")).strip()
    record_id = str(obj.get("id", "")).strip()
    label = str(obj.get("label", "")).strip().upper()
    if (review_id, record_id) not in expected:
        return None
    if label not in ALLOWED:
        return None
    rationale = str(obj.get("rationale") or obj.get("notes") or "").strip()
    if not rationale:
        return None
    confidence = obj.get("confidence")
    try:
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            confidence = None
    except (TypeError, ValueError):
        confidence = None
    return {
        "review_id": review_id,
        "id": record_id,
        "label": label,
        "confidence": confidence,
        "rationale": rationale,
    }


def parse_pass(
    run_dir: Path,
    pass_key: str,
    expected: Dict[Tuple[str, str], dict],
) -> Tuple[Dict[Tuple[str, str], dict], Dict[str, dict]]:
    parsed: Dict[Tuple[str, str], dict] = {}
    batch_stats: Dict[str, dict] = {}
    stdout_dir = run_dir / "stdout"
    status_dir = run_dir / "status"
    for status in sorted(status_dir.glob(f"pass_{pass_key}_batch_*.txt")):
        slug = status.stem
        stdout = stdout_dir / f"{slug}.txt"
        info: dict = {"slug": slug, "exit_code": None, "valid": 0, "malformed": 0}
        try:
            status_text = status.read_text(encoding="utf-8")
            match = re.search(r"exit_code=(\d+)", status_text)
            if match:
                info["exit_code"] = int(match.group(1))
        except OSError:
            pass
        if stdout.exists():
            for obj in parse_output(stdout):
                row = normalize_object(obj, expected)
                if row is None:
                    info["malformed"] += 1
                    continue
                key = (row["review_id"], row["id"])
                if key in parsed:
                    info["malformed"] += 1
                    continue
                parsed[key] = row
                info["valid"] += 1
        batch_stats[slug] = info
    return parsed, batch_stats


def cohen_kappa(left: Sequence[str], right: Sequence[str]) -> float:
    count = len(left)
    if count == 0:
        return 1.0
    observed = sum(a == b for a, b in zip(left, right)) / count
    dist_a, dist_b = Counter(left), Counter(right)
    expected = sum((dist_a[label] / count) * (dist_b[label] / count) for label in ALLOWED)
    return (observed - expected) / (1.0 - expected) if expected < 1.0 else 1.0


def adjudication_prompt(rows: Sequence[dict], guide: str) -> str:
    records = [
        {
            "review_id": row["review_id"],
            "id": row["id"],
            "text": row["text"],
            "pass_a_label": row["a_label"],
            "pass_a_confidence": row["a_conf"],
            "pass_b_label": row["b_label"],
            "pass_b_confidence": row["b_conf"],
        }
        for row in rows
    ]
    return "\n".join(
        [
            f"ANNOTATOR_ID: {PASS_C_ID}",
            "TASK: independent third-label adjudication of two blind annotators",
            "Read each message independently, then decide the label. You may agree with A or B or choose a different label; if different, explain why in rationale.",
            'Return exactly one JSON object per input row as JSONL: {"review_id":"...","id":"...","label":"TRANSACTION|AD|HARASS|FRAUD|NEEDS_REVIEW","confidence":0.0,"rationale":"..."}.',
            "confidence must be between 0 and 1. rationale must be non-empty Chinese text.",
            "LABELING GUIDE:",
            guide.strip(),
            "INPUT RECORDS:",
            json.dumps(records, ensure_ascii=False, separators=(",", ":")),
            "",
        ]
    )


def adjudication_runner_text(
    prompt: Path,
    stdout: Path,
    stderr: Path,
    status: Path,
    timeout: int = 1800,
) -> str:
    quoted_prompt = str(prompt).replace("'", "'\\''")
    command = f'opencode run -m {PASS_C_MODEL} "$(cat {quoted_prompt})"'
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -u -o pipefail",
            f'STDOUT="{stdout}"',
            f'STDERR="{stderr}"',
            f'STATUS="{status}"',
            f"mkdir -p {stdout.parent} {stderr.parent} {status.parent}",
            "attempt=0",
            "rc=0",
            "while true; do",
            "  attempt=$((attempt + 1))",
            "  started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
            "  monitor() {",
            "    local prev=0",
            "    local idle=0",
            "    while true; do",
            "      sleep 60",
            '      local cur=$(wc -c < "$STDOUT" 2>/dev/null || echo 0)',
            '      if [[ "$cur" -ne "$prev" ]]; then prev="$cur"; idle=0; else idle=$((idle + 60)); fi',
            f'      if [[ $idle -ge 900 ]]; then pkill -f "[o]pencode run -m {PASS_C_MODEL}" 2>/dev/null || true; break; fi',
            "    done",
            "  }",
            "  monitor &",
            "  monitor_pid=$!",
            "  set +e",
            f"  timeout --foreground --signal=TERM {timeout} bash -ic '{command}' >\"$STDOUT\" 2>\"$STDERR\"",
            "  rc=$?",
            '  kill "$monitor_pid" 2>/dev/null || true',
            "  set -e",
            '  if [[ $rc -eq 0 && -s "$STDOUT" ]]; then break; fi',
            "  if [[ $attempt -ge 3 ]]; then break; fi",
            "  sleep 10",
            "done",
            "ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
            'saved_path=$(grep -oE \'/[^ `]+\\.jsonl\' "$STDOUT" 2>/dev/null | head -1 || true)',
            'if [[ -n "$saved_path" && -f "$saved_path" ]]; then cp -f "$saved_path" "$STDOUT"; fi',
            "{",
            f"  printf 'model={PASS_C_MODEL}\\n'",
            "  printf 'attempts=%s\\n' \"$attempt\"",
            "  printf 'started_at=%s\\n' \"$started_at\"",
            "  printf 'ended_at=%s\\n' \"$ended_at\"",
            "  printf 'exit_code=%s\\n' \"$rc\"",
            f'  sha256sum "{prompt}" "$STDOUT" "$STDERR"',
            '} >"$STATUS"',
            "exit \"$rc\"",
            "",
        ]
    )


def merge_ab(run_dir: Path) -> int:
    blind = load_jsonl(run_dir / "blind_rows.jsonl")
    expected = {(row["review_id"], row["id"]): row for row in blind}
    by_id = {row["id"]: row for row in blind}
    if len(by_id) != len(blind):
        raise SystemExit("blind_rows contain duplicate ids; review_id/id must be 1:1")

    pass_a, stats_a = parse_pass(run_dir, "a", expected)
    pass_b, stats_b = parse_pass(run_dir, "b", expected)
    write_jsonl(run_dir / "parsed" / "pass_a.jsonl", sorted(pass_a.values(), key=lambda r: r["review_id"]))
    write_jsonl(run_dir / "parsed" / "pass_b.jsonl", sorted(pass_b.values(), key=lambda r: r["review_id"]))

    common = sorted(set(pass_a) & set(pass_b))
    labels_a = [pass_a[key]["label"] for key in common]
    labels_b = [pass_b[key]["label"] for key in common]
    exact_agreement = sum(a == b for a, b in zip(labels_a, labels_b)) / len(common) if common else 0.0
    kappa = cohen_kappa(labels_a, labels_b)

    conflicts: List[dict] = []
    for key in common:
        a = pass_a[key]
        b = pass_b[key]
        a_conf = a["confidence"] if a["confidence"] is not None else 0.0
        b_conf = b["confidence"] if b["confidence"] is not None else 0.0
        low_conf = min(a_conf, b_conf) < LOW_CONFIDENCE_THRESHOLD
        mismatch = a["label"] != b["label"]
        if mismatch or low_conf:
            reasons = []
            if mismatch:
                reasons.append("LABEL_MISMATCH")
            if low_conf:
                reasons.append("LOW_CONFIDENCE")
            row = dict(by_id[key[1]])
            row.update(
                {
                    "a_label": a["label"],
                    "a_conf": a_conf,
                    "b_label": b["label"],
                    "b_conf": b_conf,
                    "reason": "|".join(reasons),
                }
            )
            conflicts.append(row)
    conflicts.sort(key=lambda row: row["review_id"])
    write_jsonl(run_dir / "conflicts.jsonl", conflicts)

    (run_dir / "prompts").mkdir(exist_ok=True)
    (run_dir / "runners").mkdir(exist_ok=True)
    (run_dir / "stdout").mkdir(exist_ok=True)
    (run_dir / "stderr").mkdir(exist_ok=True)
    (run_dir / "status").mkdir(exist_ok=True)
    runners: List[Path] = []
    for batch_index, batch in enumerate(
        [conflicts[index : index + 25] for index in range(0, len(conflicts), 25)],
        start=1,
    ):
        slug = f"pass_c_batch_{batch_index:03d}"
        prompt = run_dir / "prompts" / f"{slug}.txt"
        stdout = run_dir / "stdout" / f"{slug}.txt"
        stderr = run_dir / "stderr" / f"{slug}.txt"
        status = run_dir / "status" / f"{slug}.txt"
        runner = run_dir / "runners" / f"{slug}.sh"
        prompt.write_text(adjudication_prompt(batch, GUIDE_CONDENSED), encoding="utf-8")
        runner.write_text(adjudication_runner_text(prompt, stdout, stderr, status), encoding="utf-8")
        runner.chmod(0o700)
        runners.append(runner)

    run_c = run_dir / "run_pass_c.sh"
    run_c.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -u",
                "failed=0",
                *[f"bash {runner}; rc=$?; if [[ $rc -ne 0 ]]; then failed=1; fi" for runner in runners],
                "exit $failed",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_c.chmod(0o700)

    missing_a = len(expected) - len(pass_a)
    missing_b = len(expected) - len(pass_b)
    report = {
        "run_id": run_dir.name,
        "stage": "merge_ab",
        "status": "A_B_MERGED_PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "models": {"pass_a": PASS_A_MODEL, "pass_b": PASS_B_MODEL, "pass_c": PASS_C_MODEL},
        "annotator_ids": {"pass_a": PASS_A_ID, "pass_b": PASS_B_ID, "pass_c": PASS_C_ID},
        "labeling_guide_sha256": sha256(GUIDE),
        "row_count": len(expected),
        "pass_a_valid": len(pass_a),
        "pass_b_valid": len(pass_b),
        "pass_a_missing": missing_a,
        "pass_b_missing": missing_b,
        "common_valid": len(common),
        "exact_agreement": round(exact_agreement, 6),
        "cohen_kappa": round(kappa, 6),
        "conflict_count": len(conflicts),
        "low_confidence_count": sum("LOW_CONFIDENCE" in row["reason"] for row in conflicts),
        "label_mismatch_count": sum("LABEL_MISMATCH" in row["reason"] for row in conflicts),
        "batch_stats": {"pass_a": stats_a, "pass_b": stats_b},
        "pass_c_batch_count": len(runners),
        "pass_c_prompt_shas": [sha256(run_dir / "prompts" / f"pass_c_batch_{i:03d}.txt") for i in range(1, len(runners) + 1)],
    }
    write_jsonl(run_dir / "parsed" / "blind_membership.jsonl", [])
    (run_dir / "qa_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: report[k] for k in ("status", "common_valid", "exact_agreement", "cohen_kappa", "conflict_count")}, ensure_ascii=False))
    return 0


def merge_c(run_dir: Path) -> int:
    conflicts = load_jsonl(run_dir / "conflicts.jsonl")
    expected = {(row["review_id"], row["id"]): row for row in conflicts}
    pass_c, stats_c = parse_pass(run_dir, "c", expected)
    write_jsonl(run_dir / "parsed" / "pass_c.jsonl", sorted(pass_c.values(), key=lambda r: r["review_id"]))

    fields = [
        "review_id",
        "id",
        "text",
        "a_label",
        "a_conf",
        "b_label",
        "b_conf",
        "c_label",
        "c_conf",
        "final_label",
        "reviewer_notes",
    ]
    review_rows: List[dict] = []
    for row in conflicts:
        c = pass_c.get((row["review_id"], row["id"]))
        review_rows.append(
            {
                "review_id": row["review_id"],
                "id": row["id"],
                "text": row["text"],
                "a_label": row["a_label"],
                "a_conf": row["a_conf"],
                "b_label": row["b_label"],
                "b_conf": row["b_conf"],
                "c_label": c["label"] if c else "",
                "c_conf": c["confidence"] if c else "",
                "final_label": "",
                "reviewer_notes": "",
            }
        )
    write_csv(run_dir / "user_review_table.csv", review_rows, fields)

    qa_path = run_dir / "qa_report.json"
    report = json.loads(qa_path.read_text(encoding="utf-8"))
    report.update(
        {
            "stage": "merge_c",
            "status": "USER_REVIEW_PACKAGE_READY",
            "pass_c_valid": len(pass_c),
            "pass_c_missing": len(expected) - len(pass_c),
            "pass_c_batch_stats": stats_c,
            "user_review_rows": len(review_rows),
            "user_review_csv_sha256": sha256(run_dir / "user_review_table.csv"),
            "needs_user_review": True,
        }
    )
    qa_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "user_review_rows": len(review_rows), "pass_c_valid": len(pass_c)}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=("merge-ab", "merge-c"), required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    if not (run_dir / "blind_rows.jsonl").exists():
        raise SystemExit(f"Missing blind_rows.jsonl in {run_dir}")
    if args.stage == "merge-ab":
        return merge_ab(run_dir)
    return merge_c(run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
