#!/usr/bin/env python3
"""Rerun Pass A/B batches whose freshly parsed valid count is below expected."""
from __future__ import annotations

import json
from pathlib import Path

import reconcile_ai_dual_pass_20260806 as R

ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "data" / "interim" / "annotation" / "ai_dual_pass_20260806_r1"
TIMEOUT = 1800
PASS_A_BATCH = 25
PASS_B_BATCH = 12


def clear_artifacts(slug: str) -> None:
    for name in ("stdout", "stderr", "status"):
        path = RUN_DIR / name / f"{slug}.txt"
        if path.exists():
            path.unlink()


def write_runner(slug: str, prompt: Path, model: str) -> Path:
    from prepare_ai_dual_pass_candidate_pack_20260806 import runner_text

    stdout = RUN_DIR / "stdout" / f"{slug}.txt"
    stderr = RUN_DIR / "stderr" / f"{slug}.txt"
    status = RUN_DIR / "status" / f"{slug}.txt"
    runner = RUN_DIR / "runners" / f"{slug}.sh"
    runner.write_text(
        runner_text(model, prompt, stdout, stderr, status, timeout=TIMEOUT),
        encoding="utf-8",
    )
    runner.chmod(0o700)
    return runner


def main() -> int:
    from prepare_ai_dual_pass_candidate_pack_20260806 import PASS_A_MODEL, PASS_B_MODEL

    blind = R.load_jsonl(RUN_DIR / "blind_rows.jsonl")
    expected = {(r["review_id"], r["id"]): r for r in blind}

    chunks_a = [blind[i : i + PASS_A_BATCH] for i in range(0, len(blind), PASS_A_BATCH)]
    chunks_b = [blind[i : i + PASS_B_BATCH] for i in range(0, len(blind), PASS_B_BATCH)]
    expected_count = {}
    for index, chunk in enumerate(chunks_a, start=1):
        expected_count[f"pass_a_batch_{index:03d}"] = len(chunk)
    for index, chunk in enumerate(chunks_b, start=1):
        expected_count[f"pass_b_batch_{index:03d}"] = len(chunk)

    _, stats_a = R.parse_pass(RUN_DIR, "a", expected)
    _, stats_b = R.parse_pass(RUN_DIR, "b", expected)
    stats = {**stats_a, **stats_b}

    runners = []
    plan = []
    for slug, count in sorted(expected_count.items()):
        valid = stats.get(slug, {}).get("valid", 0)
        if valid >= count:
            continue
        model = PASS_A_MODEL if slug.startswith("pass_a_") else PASS_B_MODEL
        prompt = RUN_DIR / "prompts" / f"{slug}.txt"
        clear_artifacts(slug)
        runners.append(write_runner(slug, prompt, model))
        plan.append({"slug": slug, "expected": count, "valid": valid})

    (RUN_DIR / "run_fill.sh").write_text(
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
    (RUN_DIR / "run_fill.sh").chmod(0o700)

    (RUN_DIR / "run_fill_all.sh").write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -u -o pipefail",
                'ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"',
                f'cd "{RUN_DIR}"',
                "failed=0",
                "bash run_fill.sh || failed=1",
                f'"$ROOT/.venv/bin/python" "$ROOT/training/scripts/reconcile_ai_dual_pass_20260806.py" --run-dir "$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1" --stage merge-ab || failed=1',
                "bash run_pass_c.sh || failed=1",
                f'"$ROOT/.venv/bin/python" "$ROOT/training/scripts/reconcile_ai_dual_pass_20260806.py" --run-dir "$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1" --stage merge-c || failed=1',
                "exit $failed",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (RUN_DIR / "run_fill_all.sh").chmod(0o700)
    print(json.dumps({"fill_batches": len(plan), "plan": plan}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
