#!/usr/bin/env bash
# Continue formal v2 on existing sms_formal_v2 T4 session after upload SSL blip.
set -euo pipefail
export PATH="/home/colab/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

if [[ -f "$HOME/.config/wsl-proxy.env" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/wsl-proxy.env"
fi

# API/auth (colab.research.google.com) must use the proxy in this network.
# Runtime file transfer (*.prod.colab.dev) often breaks via MITM proxy SSL — bypass only that.
export NO_PROXY="localhost,127.0.0.1,::1,.prod.colab.dev"
export no_proxy="$NO_PROXY"

SESSION="sms_formal_v2"
WIN_ROOT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier"
ROOT="$HOME/projects/Android_SMS_Classifier"
OUT_DIR="$HOME/colab_formal_v2_continue_$(date +%Y%m%d_%H%M%S)"
BUNDLE="/tmp/sms_formal_v2_bundle.tgz"
mkdir -p "$OUT_DIR"
cd "$ROOT"

echo "PROXY ${http_proxy:-none}"
echo "NO_PROXY $NO_PROXY"
colab status -s "$SESSION" | tee "$OUT_DIR/status.txt"
if ! grep -qiE 'Hardware: T4|gpu-t4' "$OUT_DIR/status.txt"; then
  echo "FATAL: expected live T4 session $SESSION" >&2
  exit 1
fi

echo "=== sync from Windows ==="
mkdir -p "$ROOT/training/data/processed" "$ROOT/training/configs" "$ROOT/training/scripts" "$ROOT/training/src" "$ROOT/training/data/manifests"
cp -f "$WIN_ROOT/training/data/processed/"*.jsonl "$ROOT/training/data/processed/"
cp -f "$WIN_ROOT/training/configs/"*.yaml "$ROOT/training/configs/"
python3 - <<'PY'
from pathlib import Path
import shutil
win = Path("/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier")
root = Path.home() / "projects/Android_SMS_Classifier"
for sub in ("scripts", "src"):
    src = win / "training" / sub
    dst = root / "training" / sub
    if dst.exists():
        for p in dst.iterdir():
            if p.is_file():
                p.unlink()
            elif p.is_dir() and p.name == "__pycache__":
                shutil.rmtree(p)
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(src)
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
print("scripts/src synced")
PY

echo "=== bundle ==="
tar -czf "$BUNDLE" \
  --exclude='training/data/raw' \
  --exclude='training/data/interim' \
  --exclude='training/artifacts' \
  --exclude='**/__pycache__' \
  --exclude='.git' \
  --exclude='android' \
  AGENTS.md Makefile README.md \
  training/configs \
  training/scripts \
  training/src \
  training/rules \
  training/requirements.lock \
  training/requirements-train.txt \
  training/data/processed \
  training/data/manifests
ls -lh "$BUNDLE"

upload_ok=0
for attempt in 1 2 3 4 5 6; do
  echo "UPLOAD_ATTEMPT $attempt"
  if [[ $attempt -ge 4 ]]; then
    echo "Trying upload without proxy"
    env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY \
      colab upload -s "$SESSION" "$BUNDLE" /content/sms_formal_v2_bundle.tgz && upload_ok=1 && break
  else
    colab upload -s "$SESSION" "$BUNDLE" /content/sms_formal_v2_bundle.tgz && upload_ok=1 && break
  fi
  sleep $((attempt * 10))
done
if [[ "$upload_ok" -ne 1 ]]; then
  echo "FATAL: upload failed" >&2
  exit 1
fi

colab exec -s "$SESSION" --timeout 180 <<'EOF' | tee "$OUT_DIR/extract.txt"
import shutil, tarfile
from pathlib import Path
root = Path("/content/Android_SMS_Classifier")
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True)
with tarfile.open("/content/sms_formal_v2_bundle.tgz", "r:gz") as t:
    t.extractall("/content")
# Ensure layout under REMOTE_ROOT
if not (root / "training").exists():
    for name in ["training", "AGENTS.md", "Makefile", "README.md"]:
        src = Path("/content") / name
        if src.exists():
            dest = root / name
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)
print("LAYOUT_OK", sorted(p.name for p in root.iterdir()))
print("TRAIN", (root/"training/data/processed/train.jsonl").exists())
print("RULES", (root/"training/rules/normalize/confusables.json").exists())
print("QFIX", "inference_input_type = tf.float32" in (root/"training/scripts/quantize_int8.py").read_text(encoding="utf-8"))
print("VFIX", "def resolve_path" in (root/"training/scripts/verify_tflite.py").read_text(encoding="utf-8"))
EOF

echo "=== install deps ==="
colab exec -s "$SESSION" --timeout 900 <<'EOF' | tee "$OUT_DIR/install.txt"
import subprocess, sys
pkgs = [
  "tensorflow>=2.16",
  "tensorflow-model-optimization",
  "torch",
  "transformers",
  "huggingface_hub",
  "numpy",
  "PyYAML",
  "scikit-learn",
  "tqdm",
  "sentencepiece",
]
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *pkgs])
import tensorflow as tf
print("TF", tf.__version__)
gpus = tf.config.list_physical_devices("GPU")
print("GPU", gpus)
assert gpus, "GPU required"
EOF

# Rebuild pipeline body from the Windows launcher script's heredoc content by re-running
# only the generate/upload/detach/poll/download/stop portion via the synced launcher file.
# Simpler: extract run_pipeline.py generation by invoking the same heredoc from a trimmed copy.
LAUNCHER="$WIN_ROOT/training/scripts/_colab_distill_e10_run.sh"
sed -i 's/\r$//' "$LAUNCHER"
export LAUNCHER OUT_DIR

# Generate run_pipeline.py from the embedded pipeline body in the launcher.
python3 - <<'PY'
from pathlib import Path
import os
launcher = Path(os.environ["LAUNCHER"])
out_dir = Path(os.environ["OUT_DIR"])
text = launcher.read_text(encoding="utf-8")
begin = 'import json, os, shutil, subprocess, sys, time, traceback\n'
end_token = '\nexport_dir = Path("/content/colab_export_formal_v2")\n'
# Include from import through write_status(done...) — find start of embedded script
idx = text.index(begin)
# The first occurrence is inside the heredoc for run_pipeline.py
# End after write_status done line
end_marker = 'write_status("done", export_zip="/content/colab_export_formal_v2.zip", zip_size=zip_size)\n'
end = text.index(end_marker, idx) + len(end_marker)
body = text[idx:end]
out = out_dir / "run_pipeline.py"
out.write_text(body, encoding="utf-8")
print("WROTE", out, "lines", len(body.splitlines()))
assert "allow_fail=True" in body
assert "sms_bytecnn_dense_int8.tflite" in body
PY

echo "=== upload pipeline script ==="
colab upload -s "$SESSION" "$OUT_DIR/run_pipeline.py" /content/run_pipeline_formal_v2.py

echo "=== detach ==="
colab exec -s "$SESSION" --timeout 180 <<'EOF' | tee "$OUT_DIR/detach.txt"
import os, signal, subprocess, time
from pathlib import Path

script = Path("/content/run_pipeline_formal_v2.py")
log = Path("/content/formal_v2_job.log")
pid_path = Path("/content/formal_v2_job.pid")
status = Path("/content/formal_v2_status.json")

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
    env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONPATH": "/content/Android_SMS_Classifier/training"},
)
pid_path.write_text(str(proc.pid), encoding="utf-8")
print("DETACHED_PID", proc.pid, flush=True)
time.sleep(3)
print("STATUS_BOOT", status.read_text(encoding="utf-8") if status.exists() else None, flush=True)
print("LOG_BOOT", log.read_text(encoding="utf-8")[-1000:] if log.exists() else None, flush=True)
EOF

echo "=== poll ==="
deadline=$((SECONDS + 18000))
state="unknown"
while (( SECONDS < deadline )); do
  if colab exec -s "$SESSION" --timeout 60 <<'EOF' >"$OUT_DIR/poll_last.txt" 2>"$OUT_DIR/poll_err.txt"
from pathlib import Path
status = Path("/content/formal_v2_status.json")
log = Path("/content/formal_v2_job.log")
pid_path = Path("/content/formal_v2_job.pid")
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
    print(text[-2500:])
EOF
  then
    cat "$OUT_DIR/poll_last.txt" | tee -a "$OUT_DIR/pipeline.log" >/dev/null
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
if [[ "$state" != "done" ]]; then
  echo "FATAL: detached job did not finish cleanly (state=$state)" >&2
  exit 1
fi

echo "=== download ==="
for attempt in 1 2 3 4 5; do
  if [[ $attempt -ge 3 ]]; then
    env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
      colab download -s "$SESSION" /content/colab_export_formal_v2.zip "$OUT_DIR/colab_export_formal_v2.zip" \
      2>&1 | tee "$OUT_DIR/download.log" && break
  else
    colab download -s "$SESSION" /content/colab_export_formal_v2.zip "$OUT_DIR/colab_export_formal_v2.zip" \
      2>&1 | tee "$OUT_DIR/download.log" && break
  fi
  echo "DOWNLOAD_RETRY $attempt"
  sleep 30
done
test -f "$OUT_DIR/colab_export_formal_v2.zip"

export OUT_DIR_FOR_COPY="$OUT_DIR"
python3 - <<'PY'
from pathlib import Path
import os
import shutil
z = Path(os.environ["OUT_DIR_FOR_COPY"]) / "colab_export_formal_v2.zip"
win = Path("/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier")
dst = win / "training" / "reports" / "colab_export_formal_v2.zip"
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(z, dst)
print("COPIED_TO", dst, dst.stat().st_size)
PY

echo "=== stop ==="
colab stop -s "$SESSION" 2>&1 | tee "$OUT_DIR/stop.log" || true
echo "DONE_OUT=$OUT_DIR"
ls -lah "$OUT_DIR"
