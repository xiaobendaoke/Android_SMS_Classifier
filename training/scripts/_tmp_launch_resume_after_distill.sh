#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/colab/.local/bin:/usr/bin:/bin"
if [[ -f "$HOME/.config/wsl-proxy.env" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/wsl-proxy.env"
fi
export NO_PROXY="localhost,127.0.0.1,::1,.prod.colab.dev"
export no_proxy="$NO_PROXY"

SESSION="sms_formal_v2"
WIN="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier"
OUT="$HOME/colab_formal_v2_resume_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
LOG="$HOME/formal_v2_resume_after_distill.log"

bash "$WIN/training/scripts/_tmp_restore_missing.sh" | tee "$OUT/restore.txt"

colab status -s "$SESSION" | tee "$OUT/status.txt"
colab upload -s "$SESSION" \
  "$WIN/training/scripts/generate_representative_manifest.py" \
  /content/Android_SMS_Classifier/training/scripts/generate_representative_manifest.py
colab upload -s "$SESSION" \
  "$WIN/training/scripts/evaluate_pipeline_stages.py" \
  /content/Android_SMS_Classifier/training/scripts/evaluate_pipeline_stages.py
colab upload -s "$SESSION" \
  "$WIN/training/scripts/quantize_int8.py" \
  /content/Android_SMS_Classifier/training/scripts/quantize_int8.py
colab upload -s "$SESSION" \
  "$WIN/training/scripts/verify_tflite.py" \
  /content/Android_SMS_Classifier/training/scripts/verify_tflite.py
colab upload -s "$SESSION" \
  "$WIN/training/configs/quantization.yaml" \
  /content/Android_SMS_Classifier/training/configs/quantization.yaml
colab upload -s "$SESSION" \
  "$WIN/training/scripts/_tmp_resume_after_distill.py" \
  /content/resume_after_distill.py

colab exec -s "$SESSION" --timeout 120 <<'EOF' | tee "$OUT/detach.txt"
import os, signal, subprocess, time
from pathlib import Path
script = Path("/content/resume_after_distill.py")
log = Path("/content/formal_v2_job.log")
pid_path = Path("/content/formal_v2_job.pid")
status = Path("/content/formal_v2_status.json")
assert script.is_file()
assert Path("/content/Android_SMS_Classifier/training/scripts/generate_representative_manifest.py").is_file()
assert Path("/content/Android_SMS_Classifier/training/artifacts/student/sms_bytecnn_fp32.keras").is_file()
if pid_path.exists():
    try:
        os.kill(int(pid_path.read_text().strip()), signal.SIGTERM)
        time.sleep(1)
    except Exception as exc:
        print("OLD_PID", type(exc).__name__, exc)
log.write_text("RESUME_AFTER_DISTILL\n", encoding="utf-8")
status.write_text('{"stage":"launching_resume"}', encoding="utf-8")
out = open(log, "a", buffering=1)
proc = subprocess.Popen(
    ["/usr/bin/python3", "-u", str(script)],
    stdout=out,
    stderr=subprocess.STDOUT,
    start_new_session=True,
    cwd="/content/Android_SMS_Classifier",
    env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONPATH": "/content/Android_SMS_Classifier/training"},
)
pid_path.write_text(str(proc.pid), encoding="utf-8")
print("DETACHED_PID", proc.pid, flush=True)
time.sleep(2)
print("STATUS", status.read_text(encoding="utf-8"), flush=True)
print("LOG_BOOT", log.read_text(encoding="utf-8")[-800:], flush=True)
EOF

# poll + download
deadline=$((SECONDS + 7200))
state=unknown
while (( SECONDS < deadline )); do
  if colab exec -s "$SESSION" --timeout 60 <<'EOF' >"$OUT/poll_last.txt" 2>"$OUT/poll_err.txt"
from pathlib import Path
print(Path("/content/formal_v2_status.json").read_text(encoding="utf-8"))
pid=Path("/content/formal_v2_job.pid").read_text().strip()
import os
alive=False
try:
  os.kill(int(pid),0); alive=True
except Exception:
  pass
print("PID_ALIVE", alive)
print("LOG_TAIL")
print(Path("/content/formal_v2_job.log").read_text(errors="replace")[-2000:])
print("ZIP", Path("/content/colab_export_formal_v2.zip").exists())
EOF
  then
    cat "$OUT/poll_last.txt" | tee -a "$LOG" >/dev/null
    tail -n 30 "$OUT/poll_last.txt"
    if grep -qE '"stage": "?done"?' "$OUT/poll_last.txt"; then state=done; break; fi
    if grep -qE '"stage": "?failed"?' "$OUT/poll_last.txt"; then state=failed; break; fi
  else
    echo "POLL_RETRY $(date -Is)" | tee -a "$LOG"
  fi
  sleep 90
done
echo "POLL_STATE=$state" | tee -a "$LOG"
[[ "$state" == "done" ]]

colab download -s "$SESSION" /content/colab_export_formal_v2.zip "$OUT/colab_export_formal_v2.zip"
cp -f "$OUT/colab_export_formal_v2.zip" "$WIN/training/reports/colab_export_formal_v2.zip"
ls -lh "$WIN/training/reports/colab_export_formal_v2.zip"
echo "COPIED_TO $WIN/training/reports/colab_export_formal_v2.zip"
colab stop -s "$SESSION" || true
echo DONE
