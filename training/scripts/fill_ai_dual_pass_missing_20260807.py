#!/usr/bin/env python3
"""Rerun Pass A with 12-row batches; rerun only deficient Pass B batches; then re-merge."""
from __future__ import annotations

import json
from pathlib import Path

from prepare_ai_dual_pass_candidate_pack_20260806 import (
    GUIDE_CONDENSED,
    PASS_A_ID,
    PASS_A_MODEL,
    PASS_B_ID,
    PASS_B_MODEL,
    prompt_text,
    runner_text,
)

ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = ROOT / "data" / "interim" / "annotation" / "ai_dual_pass_20260806_r1"
TIMEOUT = 1800
BATCH_SIZE = 12


def status_ok(slug: str) -> bool:
    status = RUN_DIR / "status" / f"{slug}.txt"
    return status.exists() and "exit_code=0" in status.read_text(encoding="utf-8", errors="replace")


def clear_artifacts(slug: str) -> None:
    for name in ("stdout", "stderr", "status"):
        path = RUN_DIR / name / f"{slug}.txt"
        if path.exists():
            path.unlink()


def prepare_batch(pass_key: str, rows: list[dict], model: str, annotator_id: str, index: int) -> Path:
    slug = f"pass_{pass_key}_batch_{index:03d}"
    prompt = RUN_DIR / "prompts" / f"{slug}.txt"
    prompt.write_text(prompt_text(annotator_id, rows, GUIDE_CONDENSED), encoding="utf-8")
    clear_artifacts(slug)
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
    blind = [json.loads(line) for line in (RUN_DIR / "blind_rows.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    chunks = [blind[i : i + BATCH_SIZE] for i in range(0, len(blind), BATCH_SIZE)]
    runners: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        slug = f"pass_a_batch_{index:03d}"
        if status_ok(slug):
            continue
        runners.append(prepare_batch("a", chunk, PASS_A_MODEL, PASS_A_ID, index))
    for index, chunk in enumerate(chunks, start=1):
        slug = f"pass_b_batch_{index:03d}"
        if status_ok(slug):
            continue
        runners.append(prepare_batch("b", chunk, PASS_B_MODEL, PASS_B_ID, index))

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
    print(json.dumps({"batches": len(runners), "batch_size": BATCH_SIZE}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
