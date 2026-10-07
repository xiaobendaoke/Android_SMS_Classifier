#!/usr/bin/env bash
# Resume after a failed detach: re-upload pipeline, detach job, poll, download.
set -euo pipefail
export PATH="/home/colab/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

if [[ -f "$HOME/.config/wsl-proxy.env" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/wsl-proxy.env"
fi
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}localhost,127.0.0.1,::1,.prod.colab.dev"
export no_proxy="$NO_PROXY"

SESSION="sms_recall_v3"
OUT_DIR="$(ls -dt "$HOME"/colab_recall_v3_*/ 2>/dev/null | head -n 1)"
OUT_DIR="${OUT_DIR%/}"
if [[ -z "$OUT_DIR" || ! -f "$OUT_DIR/run_pipeline.py" ]]; then
  echo "FATAL: missing OUT_DIR/run_pipeline.py" >&2
  exit 1
fi
echo "OUT_DIR=$OUT_DIR"
echo "PROXY ${http_proxy:-none}"

upload_with_retry() {
  local src="$1" dest="$2"
  local attempt
  for attempt in 1 2 3 4 5; do
    echo "UPLOAD_ATTEMPT $attempt -> $dest"
    if colab upload -s "$SESSION" "$src" "$dest"; then
      return 0
    fi
    if (( attempt >= 2 )); then
      (
        unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
        export NO_PROXY="*"
        export no_proxy="*"
        colab upload -s "$SESSION" "$src" "$dest"
      ) && return 0
    fi
    sleep $((attempt * 10))
  done
  return 1
}

echo "=== session status ==="
colab status -s "$SESSION" 2>&1 | tee "$OUT_DIR/status_reattach.txt"

echo "=== re-upload pipeline ==="
upload_with_retry "$OUT_DIR/run_pipeline.py" /content/run_pipeline_recall_v3.py

echo "=== detach with retries ==="
detached=0
for attempt in 1 2 3 4 5 6; do
  echo "DETACH_ATTEMPT $attempt"
  if colab exec -s "$SESSION" --timeout 180 <<'EOF' | tee "$OUT_DIR/detach.txt"
import os, signal, subprocess, time
from pathlib import Path

script = Path("/content/run_pipeline_recall_v3.py")
log = Path("/content/recall_v3_job.log")
pid_path = Path("/content/recall_v3_job.pid")
status = Path("/content/recall_v3_status.json")
assert script.is_file(), script

if pid_path.exists():
    try:
        old = int(pid_path.read_text().strip())
        os.kill(old, signal.SIGTERM)
        time.sleep(2)
    except Exception as exc:
        print("OLD_PID_CLEAN", type(exc).__name__, exc, flush=True)

log.write_text("", encoding="utf-8")
status.write_text('{"stage":"launching","ts":%s}' % time.time(), encoding="utf-8")
out = open(log, "a", buffering=1)
proc = subprocess.Popen(
    ["/usr/bin/python3", "-u", str(script)],
    stdout=out,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    cwd="/content/Android_SMS_Classifier",
    env={
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": "/content/Android_SMS_Classifier/training",
    },
)
pid_path.write_text(str(proc.pid), encoding="utf-8")
print("DETACHED_PID", proc.pid, flush=True)
time.sleep(5)
print("STATUS_BOOT", status.read_text(encoding="utf-8") if status.exists() else None, flush=True)
print("LOG_BOOT", log.read_text(encoding="utf-8")[-1500:] if log.exists() else None, flush=True)
EOF
  then
    if grep -q 'DETACHED_PID' "$OUT_DIR/detach.txt"; then
      detached=1
      break
    fi
  fi
  echo "DETACH_RETRY after connection blip"
  sleep $((attempt * 15))
done
if [[ "$detached" -ne 1 ]]; then
  echo "FATAL: could not detach pipeline" >&2
  exit 1
fi

echo "=== poll status ==="
deadline=$((SECONDS + 21600))
state="unknown"
while (( SECONDS < deadline )); do
  if timeout 90 colab exec -s "$SESSION" --timeout 60 <<'EOF' >"$OUT_DIR/poll_last.txt" 2>"$OUT_DIR/poll_err.txt"
from pathlib import Path
status = Path("/content/recall_v3_status.json")
log = Path("/content/recall_v3_job.log")
pid_path = Path("/content/recall_v3_job.pid")
print("STATUS_JSON", status.read_text(encoding="utf-8") if status.exists() else "MISSING")
print("PID_FILE", pid_path.read_text(encoding="utf-8").strip() if pid_path.exists() else "MISSING")
alive = False
if pid_path.exists():
    try:
        import os
        os.kill(int(pid_path.read_text().strip()), 0)
        alive = True
    except Exception:
        alive = False
print("PID_ALIVE", alive)
if log.exists():
    text = log.read_text(encoding="utf-8", errors="replace")
    print("LOG_BYTES", len(text))
    print("LOG_TAIL")
    print(text[-3000:])
EOF
  then
    cat "$OUT_DIR/poll_last.txt" >>"$OUT_DIR/pipeline.log"
    tail -n 40 "$OUT_DIR/poll_last.txt"
    if grep -qE '"stage": "?done"?' "$OUT_DIR/poll_last.txt"; then
      state="done"
      break
    fi
    if grep -qE '"stage": "?failed"?' "$OUT_DIR/poll_last.txt"; then
      state="failed"
      break
    fi
    if grep -q 'PID_ALIVE False' "$OUT_DIR/poll_last.txt"; then
      if ! grep -qE '"stage": "?(done|failed|launching)"?' "$OUT_DIR/poll_last.txt"; then
        echo "DETACHED_PROCESS_DEAD" | tee -a "$OUT_DIR/pipeline.log"
        state="dead"
        break
      fi
    fi
  else
    echo "POLL_RETRY network/cli blip at $(date -Is)" | tee -a "$OUT_DIR/pipeline.log"
    cat "$OUT_DIR/poll_err.txt" >>"$OUT_DIR/pipeline.log" || true
  fi
  sleep 120
done
echo "POLL_STATE=$state" | tee -a "$OUT_DIR/pipeline.log"

echo "=== download ==="
for attempt in 1 2 3 4 5; do
  if colab download -s "$SESSION" /content/colab_export_recall_v3.zip "$OUT_DIR/colab_export_recall_v3.zip" 2>&1 | tee "$OUT_DIR/download.log"; then
    break
  fi
  (
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    export NO_PROXY="*"
    export no_proxy="*"
    colab download -s "$SESSION" /content/colab_export_recall_v3.zip "$OUT_DIR/colab_export_recall_v3.zip"
  ) && break
  sleep 30
done
colab download -s "$SESSION" /content/recall_v3_job.log "$OUT_DIR/recall_v3_job.log" 2>/dev/null || true
colab download -s "$SESSION" /content/recall_v3_status.json "$OUT_DIR/recall_v3_status.json" 2>/dev/null || true

python3 - <<'PY'
from pathlib import Path
import shutil
outs = sorted(Path.home().glob("colab_recall_v3_*/colab_export_recall_v3.zip"))
win = Path("/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier")
reports = win / "training" / "reports"
reports.mkdir(parents=True, exist_ok=True)
if outs:
    z = outs[-1]
    dst = reports / "colab_export_recall_v3.zip"
    shutil.copy2(z, dst)
    print("COPIED_TO", dst, dst.stat().st_size)
else:
    print("NO_EXPORT_ZIP")
latest = sorted(Path.home().glob("colab_recall_v3_*"))[-1]
for name in ("recall_v3_job.log", "recall_v3_status.json", "pipeline.log"):
    src = latest / name
    if src.exists():
        shutil.copy2(src, reports / name)
        print("COPIED", name)
PY

colab stop -s "$SESSION" 2>&1 | tee "$OUT_DIR/stop.log" || true
echo "DONE_OUT=$OUT_DIR"
if [[ "$state" != "done" ]]; then
  echo "FATAL: detached job did not finish cleanly (state=$state)" >&2
  exit 1
fi
echo "RECALL_V3_OK"
