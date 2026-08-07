#!/usr/bin/env python3
"""Prepare NVIDIA dual-pass blind annotation candidate packs.

Sources:
- training/data/interim/annotation/label_conflicts_v2/conflict_pool.csv (480)
- training/data/interim/annotation/transaction_specialist_v2/specialist_pool_internal.csv (600)

Output (gitignored interim):
- training/data/interim/annotation/ai_dual_pass_20260806_r1/
  - blind_rows.jsonl
  - batches/batch_XXX.jsonl
  - prompts/pass_{a,b}_batch_XXX.txt
  - runners/pass_{a,b}_batch_XXX.sh
  - run_pass_a.sh / run_pass_b.sh / run_all.sh
  - manifest.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable


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
ALLOWED = ("TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW")

GUIDE_CONDENSED = """四分类唯一判断顺序（逐条短信只判一次主意图）：
1) 是否在骗（冒充/假奖励/索要验证码或转账/钓鱼链接） -> FRAUD
2) 是否业务结果告知（账户/订单/认证/物流/运营商/还款） -> TRANSACTION
3) 是否正规商家促销（办卡/优惠/会员/宽带） -> AD
4) 是否催收/灰产/成人/赌博/强行推销（不靠骗转账） -> HARASS
5) 其他或不确定 -> NEEDS_REVIEW
注意：看到银行/验证码/链接不等于事务或诈骗；按正文主意图判断；每条只选一个标签；吃不准就 NEEDS_REVIEW。"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def chunks(rows: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def prompt_text(pass_id: str, rows: list[dict], guide: str) -> str:
    records = [
        {"review_id": row["review_id"], "id": row["id"], "text": row["text"]}
        for row in rows
    ]
    return "\n".join(
        [
            f"ANNOTATOR_ID: {pass_id}",
            "TASK: blind four-class SMS annotation",
            "You are an automated blind SMS annotator. Read every full message independently.",
            "You receive only review_id, id, text, and this labeling guide. Do not infer prior labels, model predictions, scores, test membership, or another pass.",
            "Return exactly one JSON object per input row as JSONL. Do not use markdown, prose before or after the JSONL, or code fences.",
            'Each object must be: {"review_id":"...","id":"...","label":"TRANSACTION|AD|HARASS|FRAUD|NEEDS_REVIEW","confidence":0.0,"rationale":"..."}.',
            "confidence must be a number between 0 and 1. Lower it when uncertain; never inflate it.",
            "rationale must be non-empty Chinese text stating the primary intent and decisive evidence.",
            "Follow this mandatory decision order: 1) is it fraud (fake identity/fake reward/asking for code or money/phishing) -> FRAUD; 2) is it a business result notice (account/order/auth/logistics/carrier) -> TRANSACTION; 3) is it a legitimate merchant promotion -> AD; 4) is it collection/grey-industry/adult/gambling harassment -> HARASS; 5) otherwise NEEDS_REVIEW.",
            "Never label surveys or satisfaction requests as TRANSACTION. Active loan marketing is not TRANSACTION. Do not call FRAUD without fraud evidence. Garbled content must be NEEDS_REVIEW.",
            "LABELING GUIDE:",
            guide.strip(),
            "INPUT RECORDS:",
            json.dumps(records, ensure_ascii=False, separators=(",", ":")),
            "",
        ]
    )


def runner_text(
    model: str,
    prompt: Path,
    stdout: Path,
    stderr: Path,
    status: Path,
    timeout: int = 3600,
) -> str:
    quoted_prompt = str(prompt).replace("'", "'\\''")
    command = f'opencode run -m {model} "$(cat {quoted_prompt})"'
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
            "  set +e",
            f"  timeout --foreground --signal=TERM {timeout} bash -ic '{command}' >\"$STDOUT\" 2>\"$STDERR\"",
            "  rc=$?",
            "  set -e",
            '  if [[ $rc -eq 0 && -s "$STDOUT" ]]; then break; fi',
            "  if [[ $attempt -ge 3 ]]; then break; fi",
            "  sleep 10",
            "done",
            "ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
            'saved_path=$(grep -oE \'/[^ `]+\\.jsonl\' "$STDOUT" 2>/dev/null | head -1 || true)',
            'if [[ -n "$saved_path" && -f "$saved_path" ]]; then cp -f "$saved_path" "$STDOUT"; fi',
            "{",
            f"  printf 'model={model}\\n'",
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


def parallel_run_script(runners: list[Path], concurrency: int = 4) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -u",
        "failed=0",
        "running=()",
        "i=0",
    ]
    for runner in runners:
        lines += [
            f"bash {runner} &",
            "running+=($!)",
            "i=$((i + 1))",
            f"if [[ $i -ge {concurrency} ]]; then",
            "  for pid in \"${running[@]}\"; do wait \"$pid\" || failed=1; done",
            "  running=()",
            "  i=0",
            "fi",
        ]
    lines += [
        "for pid in \"${running[@]}\"; do wait \"$pid\" || failed=1; done",
        "exit $failed",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID_DEFAULT)
    parser.add_argument("--batch-size-a", type=int, default=50)
    parser.add_argument("--batch-size-b", type=int, default=25)
    args = parser.parse_args()
    if not 10 <= args.batch_size_a <= 100 or not 10 <= args.batch_size_b <= 100:
        raise SystemExit("--batch-size-a/--batch-size-b must be between 10 and 100")

    out = ROOT / "data" / "interim" / "annotation" / args.run_id
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing run: {out}")

    guide = GUIDE.read_text(encoding="utf-8")
    packs = [
        (
            "label_conflicts",
            "review_group_id",
            ROOT / "data/interim/annotation/label_conflicts_v2/conflict_pool.csv",
        ),
        (
            "transaction_specialist",
            "review_id",
            ROOT / "data/interim/annotation/transaction_specialist_v2/specialist_pool_internal.csv",
        ),
    ]

    rows: list[dict] = []
    inputs: dict[str, dict] = {}
    for name, key_field, path in packs:
        source_rows = read_csv(path)
        if not source_rows or key_field not in source_rows[0]:
            raise SystemExit(f"Invalid pool schema: {path}")
        inputs[name] = {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256(path),
            "count": len(source_rows),
        }
        for row in source_rows:
            review_id = (row.get(key_field) or "").strip()
            record_id = (row.get("id") or "").strip()
            text = (row.get("text") or "").strip()
            if not review_id or not record_id or not text:
                raise SystemExit(f"Missing key/id/text in {path}: review_id={review_id!r} id={record_id!r}")
            rows.append(
                {
                    "review_id": review_id,
                    "id": record_id,
                    "text": text,
                    "source": name,
                }
            )

    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["review_id"], row["id"])
        if key in seen:
            raise SystemExit(f"Duplicate review_id/id pair: {key[0]}/{key[1]}")
        seen.add(key)
    rows.sort(key=lambda row: (row["review_id"], row["id"]))

    blind_path = out / "blind_rows.jsonl"
    (out / "batches").mkdir(parents=True)
    (out / "prompts").mkdir()
    (out / "runners").mkdir()
    (out / "stdout").mkdir()
    (out / "stderr").mkdir()
    (out / "status").mkdir()

    blind_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    manifest: dict = {
        "run_id": args.run_id,
        "status": "PREPARED_PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "models": {"pass_a": PASS_A_MODEL, "pass_b": PASS_B_MODEL, "pass_c": PASS_C_MODEL},
        "annotator_ids": {"pass_a": PASS_A_ID, "pass_b": PASS_B_ID, "pass_c": PASS_C_ID},
        "labeling_guide_sha256": sha256(GUIDE),
        "batch_sizes": {"pass_a": args.batch_size_a, "pass_b": args.batch_size_b},
        "guide": {
            "full_sha256": sha256(GUIDE),
            "pass_a_guide": "condensed",
            "pass_b_guide": "condensed",
            "pass_c_guide": "condensed",
        },
        "row_count": len(rows),
        "blind_rows_sha256": sha256(blind_path),
        "inputs": inputs,
        "batches": [],
    }

    batch_sizes = {"a": args.batch_size_a, "b": args.batch_size_b}
    guides = {"a": GUIDE_CONDENSED, "b": GUIDE_CONDENSED}
    for pass_key, pass_id, model in (("a", PASS_A_ID, PASS_A_MODEL), ("b", PASS_B_ID, PASS_B_MODEL)):
        runners: list[Path] = []
        for batch_index, batch in enumerate(chunks(rows, batch_sizes[pass_key]), start=1):
            slug = f"pass_{pass_key}_batch_{batch_index:03d}"
            batch_path = out / "batches" / f"{pass_key}_batch_{batch_index - 1:03d}.jsonl"
            prompt = out / "prompts" / f"{slug}.txt"
            stdout = out / "stdout" / f"{slug}.txt"
            stderr = out / "stderr" / f"{slug}.txt"
            status = out / "status" / f"{slug}.txt"
            runner = out / "runners" / f"{slug}.sh"

            batch_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in batch),
                encoding="utf-8",
            )
            prompt.write_text(prompt_text(pass_id, batch, guides[pass_key]), encoding="utf-8")
            runner.write_text(
                runner_text(model, prompt, stdout, stderr, status),
                encoding="utf-8",
            )
            runner.chmod(0o700)
            runners.append(runner)
            manifest["batches"].append(
                {
                    "batch_index": batch_index,
                    "pass": pass_key,
                    "model": model,
                    "annotator_id": pass_id,
                    "count": len(batch),
                    "batch_sha256": sha256(batch_path),
                    "prompt_sha256": sha256(prompt),
                    "runner": str(runner.relative_to(out)).replace("\\", "/"),
                    "review_id_set_sha256": text_sha(
                        json.dumps(sorted(row["review_id"] for row in batch), ensure_ascii=False)
                    ),
                }
            )

        run_script = out / f"run_pass_{pass_key}.sh"
        run_script.write_text(parallel_run_script(runners, concurrency=4), encoding="utf-8")
        run_script.chmod(0o700)

    run_all = out / "run_all.sh"
    out_rel = out.relative_to(ROOT)
    run_pass_a_rel = out_rel / "run_pass_a.sh"
    run_pass_b_rel = out_rel / "run_pass_b.sh"
    run_pass_c_rel = out_rel / "run_pass_c.sh"
    run_all.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -u -o pipefail",
                'ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd -P)}"',
                "cd \"$ROOT\"",
                "failed=0",
                f"bash \"$ROOT/training/{run_pass_a_rel}\"; rc_a=$?",
                f"bash \"$ROOT/training/{run_pass_b_rel}\"; rc_b=$?",
                "export PYTHONPATH=\"$ROOT/training\"",
                f"\"$ROOT/.venv/bin/python\" \"$ROOT/training/scripts/reconcile_ai_dual_pass_20260806.py\" --run-dir \"$ROOT/training/{out_rel}\" --stage merge-ab || failed=1",
                f"bash \"$ROOT/training/{run_pass_c_rel}\" || failed=1",
                f"\"$ROOT/.venv/bin/python\" \"$ROOT/training/scripts/reconcile_ai_dual_pass_20260806.py\" --run-dir \"$ROOT/training/{out_rel}\" --stage merge-c || failed=1",
                "if [[ $rc_a -ne 0 || $rc_b -ne 0 ]]; then failed=1; fi",
                "exit $failed",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_all.chmod(0o700)

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "row_count": len(rows),
                "pass_a_batch_count": sum(1 for item in manifest["batches"] if item["pass"] == "a"),
                "pass_b_batch_count": sum(1 for item in manifest["batches"] if item["pass"] == "b"),
                "claim_allowed": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
