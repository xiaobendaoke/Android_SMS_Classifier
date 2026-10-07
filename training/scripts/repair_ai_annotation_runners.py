#!/usr/bin/env python3
"""Repair generated runners before any model call has completed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare_ai_annotation_run import ROOT, runner_text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="ai_annotation_20260802_r1")
    args = parser.parse_args()
    out = ROOT / "data/interim/annotation/automated_runs" / args.run_id
    manifest = json.loads((out / "automated_annotation_manifest.json").read_text(encoding="utf-8"))
    repaired = []
    for call in manifest["calls"]:
        slug = call["slug"]
        runner = out / call["runner"]
        stdout = out / "stdout" / f"{slug}.txt"
        stderr = out / "stderr" / f"{slug}.txt"
        status = out / "status" / f"{slug}.txt"
        if status.exists() or (stdout.exists() and stdout.stat().st_size) or (stderr.exists() and stderr.stat().st_size):
            raise SystemExit(f"Refusing to overwrite runner with recorded output: {slug}")
        runner.write_text(runner_text(call["model"], out / "prompts" / f"{slug}.txt", stdout, stderr, status), encoding="utf-8")
        runner.chmod(0o700)
        repaired.append(slug)
    print(json.dumps({"run_id": args.run_id, "repaired_runners": len(repaired)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
