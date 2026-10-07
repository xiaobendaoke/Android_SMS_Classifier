#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1"

ROOT="$ROOT" OUT="$OUT" "$ROOT/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path
from datetime import datetime, timezone

out = Path(os.environ["OUT"])
manifest = json.loads((out / "automated_annotation_manifest.json").read_text(encoding="utf-8"))
calls = [call for call in manifest["calls"] if call["pass"] == "c"]
summary = {"calls": len(calls), "status_ok": 0, "status_missing": 0, "status_failed": 0, "stdout_present": 0, "stderr_present": 0, "incomplete_output_files": []}
for call in calls:
    slug = call["slug"]
    status = out / "status" / f"{slug}.txt"
    stdout = out / "stdout" / f"{slug}.txt"
    stderr = out / "stderr" / f"{slug}.txt"
    if not status.exists():
        summary["status_missing"] += 1
    elif "exit_code=0" in status.read_text(encoding="utf-8"):
        summary["status_ok"] += 1
    else:
        summary["status_failed"] += 1
    summary["stdout_present"] += int(stdout.exists())
    summary["stderr_present"] += int(stderr.exists())
    if (not status.exists() or "exit_code=0" not in status.read_text(encoding="utf-8")) and stdout.exists():
        summary["incomplete_output_files"].append({"slug": slug, "bytes": stdout.stat().st_size, "modified_at": datetime.fromtimestamp(stdout.stat().st_mtime, tz=timezone.utc).isoformat()})
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
PY

count=$(pgrep -fc 'opencode run --model xfyun/xopdeepseekv4flash' || true)
printf '{"active_xopdeepseekv4flash_processes":%s}\n' "$count"
pids=$(pgrep -f '[o]pencode run --model xfyun/xopdeepseekv4flash' || true)
if [[ -n "$pids" ]]; then
  ps -o pid=,etime=,stat= -p "$pids" | awk '{printf "{\"pid\":%s,\"elapsed\":\"%s\",\"state\":\"%s\"}\n", $1, $2, $3}'
fi
