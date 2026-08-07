#!/usr/bin/env python3
"""Repair timed-out Pass A batches and rebuild Pass B sequentially.

Root cause addressed: concurrent opencode processes lock the same local database
("database is locked") and stall model builds. This repair runs strictly
sequentially with a 3600s timeout and 12-row Pass B batches.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "data" / "interim" / "annotation" / "ai_dual_pass_20260806_r1"
TIMEOUT = 3600
PASS_B_BATCH_SIZE = 12


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def status_ok(slug: str) -> bool:
    status = RUN_DIR / "status" / f"{slug}.txt"
    if not status.exists():
        return False
    return "exit_code=0" in status.read_text(encoding="utf-8", errors="replace")


def clear_artifacts(slug: str) -> None:
    for name in ("stdout", "stderr", "status"):
        path = RUN_DIR / name / f"{slug}.txt"
        if path.exists():
            path.unlink()


def write_runner(slug: str, prompt: Path, model: str) -> Path:
    stdout = RUN_DIR / "stdout" / f"{slug}.txt"
    stderr = RUN_DIR / "stderr" / f"{slug}.txt"
    status = RUN_DIR / "status" / f"{slug}.txt"
    from prepare_ai_dual_pass_candidate_pack_20260806 import runner_text

    runner = RUN_DIR / "runners" / f"{slug}.sh"
    runner.write_text(
        runner_text(model, prompt, stdout, stderr, status, timeout=TIMEOUT),
        encoding="utf-8",
    )
    runner.chmod(0o700)
    return runner


def write_sequential(script_name: str, runners: list[Path]) -> Path:
    script = RUN_DIR / script_name
    script.write_text(
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
    script.chmod(0o700)
    return script


def main() -> int:
    from prepare_ai_dual_pass_candidate_pack_20260806 import (
        PASS_A_MODEL,
        PASS_B_MODEL,
        PASS_A_ID,
        PASS_B_ID,
        GUIDE_CONDENSED,
        prompt_text,
        chunks,
    )

    if not (RUN_DIR / "blind_rows.jsonl").exists():
        raise SystemExit(f"missing {RUN_DIR / 'blind_rows.jsonl'}")

    pass_a_runners: list[Path] = []
    for prompt in sorted((RUN_DIR / "prompts").glob("pass_a_batch_*.txt")):
        slug = prompt.stem
        if not status_ok(slug):
            clear_artifacts(slug)
            pass_a_runners.append(write_runner(slug, prompt, PASS_A_MODEL))
    write_sequential("run_pass_a_repair.sh", pass_a_runners)

    blind = load_jsonl(RUN_DIR / "blind_rows.jsonl")
    pass_b_runners: list[Path] = []
    for index, batch in enumerate(chunks(blind, PASS_B_BATCH_SIZE), start=1):
        slug = f"pass_b_batch_{index:03d}"
        prompt = RUN_DIR / "prompts" / f"{slug}.txt"
        prompt.write_text(prompt_text(PASS_B_ID, batch, GUIDE_CONDENSED), encoding="utf-8")
        clear_artifacts(slug)
        pass_b_runners.append(write_runner(slug, prompt, PASS_B_MODEL))
    write_sequential("run_pass_b.sh", pass_b_runners)

    run_all = RUN_DIR / "run_repair_all.sh"
    run_all.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -u -o pipefail",
                'ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"',
                "failed=0",
                "bash run_pass_a_repair.sh || failed=1",
                "bash run_pass_b.sh || failed=1",
                f'"$ROOT/.venv/bin/python" "$ROOT/training/scripts/reconcile_ai_dual_pass_20260806.py" --run-dir "$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1" --stage merge-ab || failed=1',
                "bash run_pass_c.sh || failed=1",
                f'"$ROOT/.venv/bin/python" "$ROOT/training/scripts/reconcile_ai_dual_pass_20260806.py" --run-dir "$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1" --stage merge-c || failed=1',
                "exit $failed",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_all.chmod(0o700)

    print(
        json.dumps(
            {
                "pass_a_repair_batches": len(pass_a_runners),
                "pass_b_batches": len(pass_b_runners),
                "pass_b_batch_size": PASS_B_BATCH_SIZE,
                "timeout_seconds": TIMEOUT,
                "sequential": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
