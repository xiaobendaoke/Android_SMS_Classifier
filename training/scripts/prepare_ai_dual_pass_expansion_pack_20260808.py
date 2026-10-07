#!/usr/bin/env python3
"""Select and prepare the expanded AI dual-pass arbitration pack.

Expands arbitration coverage on the frozen zh split toward the goal target
(default 25%). Priority order:
1. All zh validation rows not already covered by a prior arbitration pack.
2. zh train rows in template groups where the failed retrain made validation errors.
3. zh train rows in template groups with boundary label mixtures.
4. A stratified fill of remaining zh train rows up to the coverage target.

No raw SMS text is written outside the gitignored interim pack; reports contain
only counts and SHAs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
GUIDE = REPO / "docs" / "labeling-guide.md"

RUN_ID_DEFAULT = "ai_dual_pass_expansion_20260808_r1"
PASS_A_MODEL = "moreai/MiniMax-M3"
PASS_B_MODEL = "moreai/MiniMax-M3"
PASS_C_MODEL = "moreai/MiniMax-M3"
PASS_A_ID = "AUTO_MOREAI_MINIMAXM3_PASS_A_001"
PASS_B_ID = "AUTO_MOREAI_MINIMAXM3_PASS_B_001"
PASS_C_ID = "AUTO_MOREAI_MINIMAXM3_ADJUDICATOR_001"
FROZEN = ROOT / "data" / "processed_v2"
RETRAIN_MODEL = (
    ROOT / "artifacts" / "experiments" / "ai_dual_pass_retrain_20260806_r1"
    / "sms_bytecnn_fp32.keras"
)

GUIDE_CONDENSED = """四分类唯一判断顺序（逐条短信只判一次主意图）：
1) 是否在骗（冒充/假奖励/索要验证码或转账/钓鱼链接） -> FRAUD
2) 是否业务结果告知（账户/订单/认证/物流/运营商/还款） -> TRANSACTION
3) 是否正规商家促销（办卡/优惠/会员/宽带） -> AD
4) 是否催收/灰产/成人/赌博/强行推销（不靠骗转账） -> HARASS
5) 其他或不确定 -> NEEDS_REVIEW
注意：看到银行/验证码/链接不等于事务或诈骗；按正文主意图判断；每条只选一个标签；吃不准就 NEEDS_REVIEW。"""

BOUNDARY_PAIRS = {
    ("FRAUD", "HARASS"),
    ("HARASS", "FRAUD"),
    ("AD", "HARASS"),
    ("HARASS", "AD"),
    ("TRANSACTION", "AD"),
    ("AD", "TRANSACTION"),
    ("FRAUD", "TRANSACTION"),
    ("TRANSACTION", "FRAUD"),
    ("AD", "FRAUD"),
    ("FRAUD", "AD"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> List[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_jsonl_ids(path: Path) -> set[str]:
    return {str(row.get("id", "")) for row in load_jsonl(path) if row.get("id")}


def load_csv_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {str(row.get("id", "")).strip() for row in csv.DictReader(handle) if row.get("id")}


def load_frozen() -> Tuple[List[dict], List[dict]]:
    train = [row for row in load_jsonl(FROZEN / "train.jsonl") if row.get("language") == "zh"]
    validation = [
        row for row in load_jsonl(FROZEN / "validation.jsonl") if row.get("language") == "zh"
    ]
    return train, validation


def load_covered_ids() -> set[str]:
    covered: set[str] = set()
    pack_roots = [
        "harass_boundary_arbitration_20260806_r1",
        "harass_fraud_boundary_arbitration_20260806_r1",
        "transaction_ad_boundary_arbitration_20260806_r1",
        "txn_boundary_r2_arbitration_20260806_r1",
    ]
    for name in pack_roots:
        path = ROOT / "data" / "interim" / "annotation" / name / "pass_a_blind.jsonl"
        if path.exists():
            covered |= load_jsonl_ids(path)
    conflict_pool = ROOT / "data" / "interim" / "annotation" / "label_conflicts_v2" / "conflict_pool.csv"
    if conflict_pool.exists():
        covered |= load_csv_ids(conflict_pool)
    blind = ROOT / "data" / "interim" / "annotation" / "ai_dual_pass_20260806_r1" / "blind_rows.jsonl"
    if blind.exists():
        covered |= load_jsonl_ids(blind)
    return covered


def error_template_groups(validation: List[dict], model_path: Path) -> set[str]:
    if not model_path.exists():
        return set()
    try:
        import numpy as np
        import tensorflow as tf

        sys.path.insert(0, str(ROOT))
        from src.schema import LABEL_ORDER
        from src.train_utils import records_to_xy, split_student_logits

        model = tf.keras.models.load_model(model_path)
        max_bytes = int(model.input_shape[-1])
        records = [
            type('_Rec', (), {'text': row.get('text', ''), 'label': row.get('label', '')})()
            for row in validation
        ]
        x, _ = records_to_xy(records, max_bytes=max_bytes)
        logits, _ = split_student_logits(np.asarray(model.predict(x, verbose=0)))
        predictions = [LABEL_ORDER[int(index)] for index in np.argmax(logits, axis=-1)]
        groups = {
            str(row.get("template_group", ""))
            for row, prediction in zip(validation, predictions)
            if row.get("label") != prediction and row.get("template_group")
        }
        return groups
    except Exception as exc:  # pragma: no cover - best effort analysis input
        print(json.dumps({"error_group_warning": str(exc)}, ensure_ascii=False))
        return set()


def boundary_template_groups(rows: List[dict]) -> set[str]:
    group_labels: Dict[str, set[str]] = defaultdict(set)
    for row in rows:
        group = str(row.get("template_group", ""))
        if group:
            group_labels[group].add(str(row.get("label", "")))
    return {
        group
        for group, labels in group_labels.items()
        if any((left, right) in BOUNDARY_PAIRS for left in labels for right in labels if left != right)
    }


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
    timeout: int = 1800,
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
            "  monitor() {",
            "    local prev=0",
            "    local idle=0",
            "    while true; do",
            "      sleep 60",
            '      local cur=$(wc -c < "$STDOUT" 2>/dev/null || echo 0)',
            '      if [[ "$cur" -ne "$prev" ]]; then prev="$cur"; idle=0; else idle=$((idle + 60)); fi',
            f'      if [[ $idle -ge 900 ]]; then pkill -f "[o]pencode run -m {model}" 2>/dev/null || true; break; fi',
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


def select_rows(
    train: List[dict],
    validation: List[dict],
    covered: set[str],
    error_groups: set[str],
    boundary_groups: set[str],
    target_total: int,
    seed: int,
) -> Tuple[List[dict], dict]:
    rng = random.Random(seed)
    by_id = {str(row["id"]): row for row in train + validation}
    selected: List[dict] = []
    seen: set[str] = set()

    def add(row: dict, source: str) -> None:
        record_id = str(row["id"])
        if record_id in covered or record_id in seen:
            return
        seen.add(record_id)
        selected.append({**row, "_source": source})

    for row in validation:
        add(row, "validation")
    for row in train:
        if str(row.get("template_group", "")) in error_groups:
            add(row, "train_error_group")
    for row in train:
        if str(row.get("template_group", "")) in boundary_groups:
            add(row, "train_boundary_group")

    remaining = [row for row in train if str(row["id"]) not in seen and str(row["id"]) not in covered]
    remaining.sort(key=lambda row: (str(row.get("label", "")), str(row.get("id", ""))))
    rng.shuffle(remaining)
    for row in remaining:
        if len(selected) >= target_total:
            break
        add(row, "train_stratified")

    source_counts = Counter(row["_source"] for row in selected)
    label_counts = Counter(row.get("label", "") for row in selected)
    return selected, {"source_counts": dict(source_counts), "label_counts": dict(label_counts)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=RUN_ID_DEFAULT)
    parser.add_argument("--target-coverage", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = ROOT / "data" / "interim" / "annotation" / args.run_id
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing run: {out}")

    train, validation = load_frozen()
    frozen_rows = train + validation
    frozen_total = len(frozen_rows)
    covered = load_covered_ids()
    covered_frozen = covered & {str(row["id"]) for row in frozen_rows}
    target_total = max(0, int(frozen_total * args.target_coverage) - len(covered_frozen))

    error_groups = error_template_groups(validation, RETRAIN_MODEL)
    boundary_groups = boundary_template_groups(train + validation)
    selected, selection_summary = select_rows(
        train,
        validation,
        covered_frozen,
        error_groups,
        boundary_groups,
        target_total,
        args.seed,
    )
    if not selected:
        raise SystemExit("No rows selected; check coverage target or covered sets.")

    rows: List[dict] = []
    for index, row in enumerate(selected, start=1):
        rows.append(
            {
                "review_id": f"exp-20260808-{index:05d}",
                "id": str(row["id"]),
                "text": str(row.get("text", "")),
                "source": row["_source"],
            }
        )
    rows.sort(key=lambda row: (row["review_id"], row["id"]))

    (out / "batches").mkdir(parents=True)
    (out / "prompts").mkdir()
    (out / "runners").mkdir()
    (out / "stdout").mkdir()
    (out / "stderr").mkdir()
    (out / "status").mkdir()

    pool_path = out / "expansion_pool.csv"
    with pool_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["review_id", "id", "text", "source"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in ("review_id", "id", "text", "source")})

    blind_path = out / "blind_rows.jsonl"
    blind_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    manifest: dict = {
        "run_id": args.run_id,
        "status": "PREPARED_EXPANSION_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "models": {"pass_a": PASS_A_MODEL, "pass_b": PASS_B_MODEL, "pass_c": PASS_C_MODEL},
        "annotator_ids": {"pass_a": PASS_A_ID, "pass_b": PASS_B_ID, "pass_c": PASS_C_ID},
        "labeling_guide_sha256": sha256(GUIDE),
        "batch_sizes": {"pass_a": 50, "pass_b": 25},
        "row_count": len(rows),
        "blind_rows_sha256": sha256(blind_path),
        "pool_sha256": sha256(pool_path),
        "selection": {
            "frozen_zh_total": frozen_total,
            "target_coverage": args.target_coverage,
            "target_new_rows": target_total,
            "covered_frozen_zh": len(covered_frozen),
            "selected": len(rows),
            **selection_summary,
            "error_template_groups": len(error_groups),
            "boundary_template_groups": len(boundary_groups),
        },
        "inputs": {"frozen_train": str(FROZEN / "train.jsonl"), "frozen_validation": str(FROZEN / "validation.jsonl")},
        "batches": [],
    }

    batch_sizes = {"a": 50, "b": 25}
    guides = {"a": GUIDE_CONDENSED, "b": GUIDE_CONDENSED}
    for pass_key, pass_id, model in (("a", PASS_A_ID, PASS_A_MODEL), ("b", PASS_B_ID, PASS_B_MODEL)):
        runners: List[Path] = []
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
                "selection": manifest["selection"],
                "pass_a_batch_count": sum(1 for item in manifest["batches"] if item["pass"] == "a"),
                "pass_b_batch_count": sum(1 for item in manifest["batches"] if item["pass"] == "b"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
