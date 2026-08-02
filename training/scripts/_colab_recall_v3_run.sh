#!/usr/bin/env bash
# Colab runner for training/scripts/run_recall_v3.py
# Local tutorial uses --teacher-model-path D:\models\bert-base-multilingual-cased;
# on Colab we download the same weights to /content/hf_cache/... then pass that path.
set -euo pipefail
export PATH="/home/colab/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

if [[ -f "$HOME/.config/wsl-proxy.env" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/wsl-proxy.env"
  echo "PROXY ${http_proxy:-none}"
fi
# API/auth needs proxy; runtime file IO to *.prod.colab.dev often breaks via MITM SSL.
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}localhost,127.0.0.1,::1,.prod.colab.dev"
export no_proxy="$NO_PROXY"
echo "NO_PROXY ${no_proxy}"

ROOT="$HOME/projects/Android_SMS_Classifier"
WIN_ROOT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier"
SESSION="sms_recall_v3"
OUT_DIR="$HOME/colab_recall_v3_$(date +%Y%m%d_%H%M%S)"
BUNDLE="/tmp/sms_recall_v3_bundle.tgz"
mkdir -p "$OUT_DIR"
cd "$ROOT"

echo "=== sync from Windows ==="
mkdir -p "$ROOT/training/data/processed" "$ROOT/training/configs" "$ROOT/training/scripts" \
  "$ROOT/training/src" "$ROOT/training/data/manifests" "$ROOT/training/rules"
cp -f "$WIN_ROOT/training/data/processed/"*.jsonl "$ROOT/training/data/processed/"
cp -f "$WIN_ROOT/training/configs/"*.yaml "$ROOT/training/configs/"
cp -f "$WIN_ROOT/training/data/manifests/"*.json "$ROOT/training/data/manifests/" 2>/dev/null || true
python3 - <<'PY'
from pathlib import Path
import shutil
win = Path("/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier")
root = Path.home() / "projects/Android_SMS_Classifier"
for sub in ("scripts", "src", "rules"):
    src = win / "training" / sub
    dst = root / "training" / sub
    if not src.exists():
        print("SKIP_MISSING", src)
        continue
    if dst.exists():
        for p in dst.iterdir():
            if p.is_file():
                p.unlink()
            elif p.is_dir() and p.name == "__pycache__":
                shutil.rmtree(p)
            elif p.is_dir():
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
print("scripts/src/rules synced")
assert (root / "training/scripts/run_recall_v3.py").is_file()
PY

echo "=== local processed counts ==="
python3 - <<'PY' | tee "$OUT_DIR/local_counts.txt"
from collections import Counter
from pathlib import Path
import json
base = Path.home()/"projects/Android_SMS_Classifier/training/data/processed"
for name in ("train.jsonl","validation.jsonl","test.jsonl"):
    labels=Counter(); n=0
    with (base/name).open(encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            n+=1
            labels[json.loads(line).get("label","?")] += 1
    print(name, n, dict(labels))
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

echo "=== new GPU session (T4 only; refuse silent CPU fallback) ==="
for old in sms_formal_v2 sms_audit_e10 sms_e10 sms_distill_e10 sms_recall_v3; do
  colab stop -s "$old" 2>/dev/null || true
done
ok=0
for attempt in 1 2 3 4 5 6; do
  echo "GPU_ATTEMPT $attempt"
  if colab new -s "$SESSION" --gpu T4; then
    status_txt="$(colab status -s "$SESSION" 2>&1 || true)"
    echo "$status_txt" | tee "$OUT_DIR/status.txt"
    if echo "$status_txt" | grep -qiE 'Hardware: T4|gpu-t4|GPU'; then
      ok=1
      break
    fi
    echo "Got non-T4 runtime; stopping and retrying"
    colab stop -s "$SESSION" 2>/dev/null || true
  fi
  sleep $((attempt * 15))
done
if [[ "$ok" -ne 1 ]]; then
  echo "FATAL: could not obtain T4 GPU after retries" >&2
  exit 1
fi

upload_with_retry() {
  local src="$1" dest="$2"
  local attempt
  for attempt in 1 2 3 4 5; do
    echo "UPLOAD_ATTEMPT $attempt -> $dest"
    if colab upload -s "$SESSION" "$src" "$dest"; then
      return 0
    fi
    # Later attempts: bypass proxy for runtime file IO.
    if (( attempt >= 2 )); then
      echo "UPLOAD_RETRY without http_proxy"
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

echo "=== upload bundle ==="
upload_with_retry "$BUNDLE" /content/sms_recall_v3_bundle.tgz

colab exec -s "$SESSION" --timeout 180 <<'EOF' | tee "$OUT_DIR/extract.txt"
import shutil, tarfile
from pathlib import Path
root = Path("/content/Android_SMS_Classifier")
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True)
with tarfile.open("/content/sms_recall_v3_bundle.tgz", "r:gz") as t:
    t.extractall("/content", filter="data")
if not (root/"training").exists() and Path("/content/training").exists():
    for name in ["training","AGENTS.md","Makefile","README.md"]:
        src = Path("/content")/name
        if src.exists():
            dest = root/name
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)
from collections import Counter
import json
base = root/"training/data/processed"
for name in ("train.jsonl","validation.jsonl","test.jsonl"):
    labels=Counter(); n=0
    with (base/name).open(encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: continue
            n+=1
            labels[json.loads(line)["label"]] += 1
    print("REMOTE", name, n, dict(labels))
assert (root/"training/scripts/run_recall_v3.py").is_file()
print("LAYOUT_OK", sorted(p.name for p in root.iterdir()))
EOF

echo "=== install deps (TF + torch + transformers) ==="
colab exec -s "$SESSION" --timeout 900 <<'EOF' | tee "$OUT_DIR/install.txt"
import os, subprocess, sys
os.environ.pop("HF_ENDPOINT", None)
os.environ.pop("HUGGINGFACE_HUB_ENDPOINT", None)
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "tensorflow>=2.16", "tensorflow-model-optimization",
    "torch", "transformers", "accelerate", "huggingface_hub",
    "numpy", "PyYAML", "scikit-learn", "tqdm",
])
import tensorflow as tf
import torch
import transformers
print("TF", tf.__version__)
print("GPU_TF", tf.config.list_physical_devices("GPU"))
print("TORCH", torch.__version__, "CUDA", torch.cuda.is_available())
print("TRANSFORMERS", transformers.__version__)
assert torch.cuda.is_available(), "CUDA required for recall_v3 teacher/student training"
assert tf.config.list_physical_devices("GPU"), "TF GPU required for student distill/quantize"
EOF

cat > "$OUT_DIR/run_pipeline.py" <<'PY'
import json, os, shutil, subprocess, sys, time, traceback
from pathlib import Path

ROOT = Path("/content/Android_SMS_Classifier")
os.chdir(ROOT)
os.environ["PYTHONPATH"] = str(ROOT / "training")
os.environ["PYTHONUNBUFFERED"] = "1"
os.environ.pop("HF_ENDPOINT", None)
os.environ.pop("HUGGINGFACE_HUB_ENDPOINT", None)
SEED = "42"
MODEL_CACHE = Path("/content/hf_cache/bert-base-multilingual-cased")
STATUS = Path("/content/recall_v3_status.json")
LOG = Path("/content/recall_v3_job.log")

def write_status(stage, **extra):
    payload = {"stage": stage, "ts": time.time(), "pid": os.getpid(), **extra}
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STATUS", stage, flush=True)

def run(*args, allow_fail=False):
    cmd = [sys.executable, "-u", *args]
    print("RUN", " ".join(cmd), flush=True)
    write_status("running", cmd=" ".join(cmd))
    p = subprocess.run(cmd, capture_output=False)
    if p.returncode != 0 and not allow_fail:
        write_status("failed", cmd=" ".join(cmd), returncode=p.returncode)
        raise SystemExit(p.returncode)
    return p.returncode

try:
    write_status("started")
    for rel in [
        "training/artifacts/teacher",
        "training/artifacts/student",
    ]:
        p = ROOT / rel
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)

    # Equivalent of local --teacher-model-path D:\models\bert-base-multilingual-cased
    MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    need_download = not (MODEL_CACHE / "config.json").exists()
    if need_download:
        write_status("download_teacher")
        print("DOWNLOAD_TEACHER_START", flush=True)
        from huggingface_hub import snapshot_download
        last_err = None
        for endpoint in (None, "https://hf-mirror.com"):
            try:
                if endpoint:
                    os.environ["HF_ENDPOINT"] = endpoint
                else:
                    os.environ.pop("HF_ENDPOINT", None)
                snapshot_download(
                    repo_id="google-bert/bert-base-multilingual-cased",
                    local_dir=str(MODEL_CACHE),
                )
                print("DOWNLOAD_TEACHER_OK", endpoint or "huggingface.co", flush=True)
                last_err = None
                break
            except Exception as e:
                last_err = e
                print("DOWNLOAD_TEACHER_FAIL", endpoint or "huggingface.co", type(e).__name__, e, flush=True)
        if last_err is not None:
            raise SystemExit(f"Failed to download teacher: {last_err}")
    else:
        print("DOWNLOAD_TEACHER_CACHED", MODEL_CACHE, flush=True)

    os.environ.pop("HF_ENDPOINT", None)
    os.environ.pop("HUGGINGFACE_HUB_ENDPOINT", None)

    write_status("run_recall_v3")
    run(
        "training/scripts/run_recall_v3.py",
        "--teacher-model-path", str(MODEL_CACHE),
        "--seed", SEED,
    )

    # Package results for download
    export_dir = Path("/content/colab_export_recall_v3")
    if export_dir.exists():
        shutil.rmtree(export_dir)
    (export_dir / "artifacts" / "student").mkdir(parents=True)
    (export_dir / "artifacts" / "teacher").mkdir(parents=True)
    (export_dir / "android_assets" / "model").mkdir(parents=True)
    student_dir = ROOT / "training/artifacts/student"
    for name in [
        "sms_bytecnn_int8.tflite",
        "sms_bytecnn_fp32.keras",
        "distill_manifest.json",
    ]:
        src = student_dir / name
        if src.exists():
            shutil.copy2(src, export_dir / "artifacts" / "student" / name)
    for src in [
        ROOT / "training/data/manifests/teacher_logits_manifest.json",
        ROOT / "training/data/manifests/teacher_manifest.json",
    ]:
        if src.exists():
            shutil.copy2(src, export_dir / "artifacts" / "teacher" / src.name)
    metrics_dir = ROOT / "training/reports/metrics"
    if metrics_dir.exists():
        shutil.copytree(metrics_dir, export_dir / "metrics", dirs_exist_ok=True)
    android_model = (
        ROOT
        / "android/classifier-sdk/src/main/assets/model/sms_bytecnn_int8.tflite"
    )
    if android_model.exists():
        shutil.copy2(android_model, export_dir / "android_assets" / "model" / android_model.name)
    shutil.make_archive("/content/colab_export_recall_v3", "zip", export_dir)
    zip_size = Path("/content/colab_export_recall_v3.zip").stat().st_size
    print("EXPORT_ZIP", zip_size, flush=True)

    summary = {
        "status": "PIPELINE_OK",
        "zip_size": zip_size,
    }
    for rel in [
        "training/artifacts/student/distill_manifest.json",
        "training/reports/metrics/student_distill.json",
        "training/reports/metrics/evaluate_recall_v3.json",
        "training/reports/metrics/verify_tflite.json",
        "training/reports/metrics/quantize.json",
    ]:
        p = ROOT / rel
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            summary[p.name] = {
                k: data.get(k)
                for k in (
                    "status",
                    "macro_f1",
                    "transaction_recall",
                    "transaction_precision",
                    "acceptance_eligible",
                    "best_epoch",
                    "val_metrics",
                    "gate_errors",
                )
                if k in data
            } or data
            print("RESULT_FILE", rel, flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    write_status("done", export_zip="/content/colab_export_recall_v3.zip", zip_size=zip_size)
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else 1
    write_status("failed", returncode=code, error=str(e))
    traceback.print_exc()
    raise
except Exception as e:
    write_status("failed", error=f"{type(e).__name__}: {e}")
    traceback.print_exc()
    raise
PY

echo "=== upload pipeline script ==="
upload_with_retry "$OUT_DIR/run_pipeline.py" /content/run_pipeline_recall_v3.py

echo "=== detach pipeline on remote VM ==="
colab exec -s "$SESSION" --timeout 180 <<'EOF' | tee "$OUT_DIR/detach.txt"
import os, signal, subprocess, time
from pathlib import Path

script = Path("/content/run_pipeline_recall_v3.py")
log = Path("/content/recall_v3_job.log")
pid_path = Path("/content/recall_v3_job.pid")
status = Path("/content/recall_v3_status.json")

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

echo "=== poll status (tolerant of local disconnects) ==="
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

# Always try to download artifacts / logs for triage when failed.
echo "=== download ==="
for attempt in 1 2 3 4 5; do
  if colab download -s "$SESSION" /content/colab_export_recall_v3.zip "$OUT_DIR/colab_export_recall_v3.zip" 2>&1 | tee "$OUT_DIR/download.log"; then
    break
  fi
  echo "DOWNLOAD_RETRY $attempt"
  (
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    export NO_PROXY="*"
    export no_proxy="*"
    colab download -s "$SESSION" /content/colab_export_recall_v3.zip "$OUT_DIR/colab_export_recall_v3.zip"
  ) && break
  sleep 30
done

# Also pull job log for local inspection.
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
# copy latest status/log if present
latest = sorted(Path.home().glob("colab_recall_v3_*"))[-1]
for name in ("recall_v3_job.log", "recall_v3_status.json", "pipeline.log"):
    src = latest / name
    if src.exists():
        shutil.copy2(src, reports / name)
        print("COPIED", name)
PY

echo "=== stop ==="
colab stop -s "$SESSION" 2>&1 | tee "$OUT_DIR/stop.log" || true
echo "DONE_OUT=$OUT_DIR"
ls -lah "$OUT_DIR"
if [[ "$state" != "done" ]]; then
  echo "FATAL: detached job did not finish cleanly (state=$state)" >&2
  exit 1
fi
echo "RECALL_V3_OK"
