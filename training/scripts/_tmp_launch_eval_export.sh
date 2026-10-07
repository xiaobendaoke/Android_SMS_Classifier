#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/colab/.local/bin:/usr/bin:/bin"
source "$HOME/.config/wsl-proxy.env"
export NO_PROXY="localhost,127.0.0.1,::1,.prod.colab.dev"
export no_proxy="$NO_PROXY"
SESSION="sms_formal_v2"
WIN="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier"
OUT="$HOME/colab_formal_v2_evalexp_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
sed -i 's/\r$//' "$WIN/training/scripts/_tmp_resume_eval_export.py"
colab upload -s "$SESSION" "$WIN/training/scripts/_tmp_resume_eval_export.py" /content/resume_eval_export.py
colab exec -s "$SESSION" --timeout 120 <<'EOF' | tee "$OUT/detach.txt"
import os, signal, subprocess, time
from pathlib import Path
script=Path("/content/resume_eval_export.py")
log=Path("/content/formal_v2_job.log")
pid_path=Path("/content/formal_v2_job.pid")
status=Path("/content/formal_v2_status.json")
assert Path("/content/Android_SMS_Classifier/training/artifacts/student/sms_bytecnn_dense_int8.tflite").is_file()
if pid_path.exists():
    try:
        os.kill(int(pid_path.read_text().strip()), signal.SIGTERM)
        time.sleep(1)
    except Exception as e:
        print("OLD", e)
log.write_text("RESUME_EVAL_EXPORT\n", encoding="utf-8")
out=open(log,"a",buffering=1)
proc=subprocess.Popen(
    ["/usr/bin/python3","-u",str(script)],
    stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
    cwd="/content/Android_SMS_Classifier",
    env={**os.environ,"PYTHONUNBUFFERED":"1","PYTHONPATH":"/content/Android_SMS_Classifier/training"},
)
pid_path.write_text(str(proc.pid), encoding="utf-8")
print("DETACHED_PID", proc.pid)
time.sleep(2)
print(status.read_text(encoding="utf-8") if status.exists() else "NO_STATUS")
print(log.read_text(errors="replace")[-1200:])
EOF

deadline=$((SECONDS + 3600))
state=unknown
while (( SECONDS < deadline )); do
  colab exec -s "$SESSION" --timeout 60 <<'EOF' >"$OUT/poll.txt" 2>"$OUT/poll.err" || true
from pathlib import Path
print(Path("/content/formal_v2_status.json").read_text(encoding="utf-8"))
print("ZIP", Path("/content/colab_export_formal_v2.zip").exists())
print("LOG_TAIL")
print(Path("/content/formal_v2_job.log").read_text(errors="replace")[-1500:])
EOF
  tail -n 40 "$OUT/poll.txt"
  if grep -qE '"stage": "?done"?' "$OUT/poll.txt"; then state=done; break; fi
  if grep -qE '"stage": "?failed"?' "$OUT/poll.txt"; then state=failed; break; fi
  sleep 45
done
echo "POLL_STATE=$state"
[[ "$state" == "done" ]]
colab download -s "$SESSION" /content/colab_export_formal_v2.zip "$OUT/colab_export_formal_v2.zip"
mkdir -p "$WIN/training/reports"
cp -f "$OUT/colab_export_formal_v2.zip" "$WIN/training/reports/colab_export_formal_v2.zip"
ls -lh "$WIN/training/reports/colab_export_formal_v2.zip"
echo "COPIED_TO $WIN/training/reports/colab_export_formal_v2.zip"
colab stop -s "$SESSION" || true
echo DONE
