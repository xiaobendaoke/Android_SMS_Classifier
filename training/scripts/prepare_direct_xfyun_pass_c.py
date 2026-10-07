#!/usr/bin/env python3
"""Prepare isolated direct-xfyun retry calls for every Pass C conflict batch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


TRAINING = Path(__file__).resolve().parent.parent
REPO = TRAINING.parent
RUN_ID = "ai_annotation_20260802_r1"
MODEL = "xopdeepseekv4flash"
OUT = TRAINING / "data/interim/annotation/automated_runs" / RUN_ID
DIRECT = OUT / "direct_xfyun_pass_c_20260803"
DEMO = "/mnt/c/Users/woshinibaba/AppData/Local/Temp/opencode/xf_demo.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runner_text(root: Path, prompt: Path, stdout: Path, stderr: Path, status: Path) -> str:
    caller = root / "training/scripts/direct_xfyun_call.py"
    return "\n".join([
        "#!/usr/bin/env bash",
        "set -u -o pipefail",
        f"mkdir -p {stdout.parent} {stderr.parent} {status.parent}",
        "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "set +e",
        f'"{root}/.venv/bin/python" "{caller}" --demo-config "{DEMO}" --model "{MODEL}" --prompt "{prompt}" >"{stdout}" 2>"{stderr}"',
        "rc=$?",
        "set -e",
        "ended_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)",
        "{",
        f"  printf 'model={MODEL}\\n'",
        "  printf 'transport=direct_openai_sdk_xfyun_v2\\n'",
        "  printf 'started_at=%s\\n' \"$started_at\"",
        "  printf 'ended_at=%s\\n' \"$ended_at\"",
        "  printf 'exit_code=%s\\n' \"$rc\"",
        f'  sha256sum "{prompt}" "{stdout}" "{stderr}"',
        f'}} >"{status}"',
        "exit \"$rc\"",
        "",
    ])


def main() -> int:
    manifest = json.loads((OUT / "automated_annotation_manifest.json").read_text(encoding="utf-8"))
    calls = [call for call in manifest["calls"] if call["pass"] == "c"]
    if len(calls) != 7:
        raise ValueError(f"expected seven Pass C calls, got {len(calls)}")
    if DIRECT.exists():
        raise ValueError(f"refusing to overwrite existing direct run: {DIRECT}")
    direct_calls = []
    runners = []
    for call in calls:
        slug = call["slug"]
        original_prompt = OUT / "prompts" / f"{slug}.txt"
        prompt = DIRECT / "prompts" / f"{slug}.txt"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_bytes(original_prompt.read_bytes())
        stdout = DIRECT / "stdout" / f"{slug}.txt"
        stderr = DIRECT / "stderr" / f"{slug}.txt"
        status = DIRECT / "status" / f"{slug}.txt"
        runner = DIRECT / "runners" / f"{slug}.sh"
        runner.parent.mkdir(parents=True, exist_ok=True)
        runner.write_text(runner_text(REPO, prompt, stdout, stderr, status), encoding="utf-8")
        runner.chmod(0o700)
        runners.append(runner)
        direct_calls.append({
            "slug": slug,
            "model": MODEL,
            "transport": "direct_openai_sdk_xfyun_v2",
            "count": call["count"],
            "input_sha256": call["input_sha256"],
            "prompt_sha256": sha256(prompt),
            "runner": str(runner.relative_to(DIRECT)),
        })
    run_all = DIRECT / "run_all.sh"
    lines = ["#!/usr/bin/env bash", "set -u", "failed=0"]
    for runner in runners:
        lines += [f'"{runner}"', "rc=$?", "if [[ $rc -ne 0 ]]; then failed=1; fi"]
    lines += ["exit $failed", ""]
    run_all.write_text("\n".join(lines), encoding="utf-8")
    run_all.chmod(0o700)
    (DIRECT / "manifest.json").write_text(json.dumps({
        "run_id": RUN_ID,
        "status": "PREPARED_PROVISIONAL_AUTOMATED_MULTI_PASS",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "model": MODEL,
        "transport": "direct_openai_sdk_xfyun_v2",
        "calls": direct_calls,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"calls": len(direct_calls), "transport": "direct_openai_sdk_xfyun_v2"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
