#!/usr/bin/env bash
# BERT teacher -> ByteCNN distill (NOT hard-only) -> prune -> quantize -> eval
# Compare against colab_export_audit_e10.zip baseline.
set -euo pipefail
export PATH="/home/colab/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# WSL2 cannot use Windows 127.0.0.1 proxy directly; use host gateway from wsl-proxy.env.
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
SESSION="sms_formal_v2"
OUT_DIR="$HOME/colab_formal_v2_$(date +%Y%m%d_%H%M%S)"
BUNDLE="/tmp/sms_formal_v2_bundle.tgz"
mkdir -p "$OUT_DIR"
cd "$ROOT"

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
colab stop -s sms_audit_e10 2>/dev/null || true
colab stop -s sms_e10 2>/dev/null || true
colab stop -s sms_distill_e10 2>/dev/null || true
colab stop -s "$SESSION" 2>/dev/null || true
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

echo "=== upload ==="
colab upload -s "$SESSION" "$BUNDLE" /content/sms_formal_v2_bundle.tgz
colab exec -s "$SESSION" --timeout 180 <<'EOF' | tee "$OUT_DIR/extract.txt"
import shutil, tarfile
from pathlib import Path
root = Path("/content/Android_SMS_Classifier")
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True)
with tarfile.open("/content/sms_formal_v2_bundle.tgz", "r:gz") as t:
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
print("LAYOUT_OK", sorted(p.name for p in root.iterdir()))
EOF

echo "=== install deps (TF + torch + transformers) ==="
colab exec -s "$SESSION" --timeout 900 <<'EOF' | tee "$OUT_DIR/install.txt"
import os, subprocess, sys
# Do NOT force hf-mirror; Colab previously failed to reach it.
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
assert torch.cuda.is_available(), "CUDA required for formal teacher/student training"
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
STATUS = Path("/content/formal_v2_status.json")
LOG = Path("/content/formal_v2_job.log")

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

# clean artifacts
write_status("started")
for rel in [
    "training/artifacts/teacher",
    "training/artifacts/student_homework_bootstrap",
    "training/artifacts/student",
]:
    p = ROOT / rel
    if p.exists():
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)

# 0) Download teacher weights to local path (avoid hub flakiness mid-train)
MODEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
need_download = not (MODEL_CACHE / "config.json").exists()
if need_download:
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

# Always train from local cache; unset mirror env for local load.
os.environ.pop("HF_ENDPOINT", None)
os.environ.pop("HUGGINGFACE_HUB_ENDPOINT", None)

# 1) Teacher BERT
run(
    "training/scripts/train_teacher.py",
    "--config", str(ROOT / "training/configs/teacher.yaml"),
    "--seed", SEED,
    "--model-path", str(MODEL_CACHE),
)
logits_manifest = ROOT / "training/data/manifests/teacher_logits_manifest.json"
assert logits_manifest.is_file(), logits_manifest
teacher_manifest = ROOT / "training/data/manifests/teacher_manifest.json"
print("TEACHER_LOGITS", json.loads(logits_manifest.read_text(encoding="utf-8")), flush=True)
if teacher_manifest.exists():
    print("TEACHER_MANIFEST_KEYS", sorted(json.loads(teacher_manifest.read_text(encoding="utf-8")).keys()), flush=True)

# 2) Distill dense student with formal student.yaml — NO --hard-only
cfg = ROOT / "training/configs/student.yaml"
student_dir = ROOT / "training/artifacts/student"
run("training/scripts/distill_student.py", "--config", str(cfg), "--seed", SEED)
dense_keras = student_dir / "sms_bytecnn_fp32.keras"
assert dense_keras.is_file(), dense_keras
hw_manifest = student_dir / "distill_manifest.json"
assert hw_manifest.is_file(), hw_manifest
distill = json.loads(hw_manifest.read_text(encoding="utf-8"))
print("DISTILL", {k: distill.get(k) for k in ("status", "used_distillation", "epochs", "alpha", "beta", "temperature")}, flush=True)
assert distill.get("status") == "OK", distill
assert distill.get("used_distillation") is True, distill

# 3) Representative set + Dense FP32 eval + Dense Full-INT8
run(
    "training/scripts/generate_representative_manifest.py",
    "--summary", "training/reports/metrics/representative_summary.json",
    "--seed", SEED,
)
run(
    "training/scripts/evaluate.py",
    "--mode", "keras",
    "--keras", "training/artifacts/student/sms_bytecnn_fp32.keras",
    "--test", "training/data/processed/validation.jsonl",
    "--stage", "dense_fp32",
    "--output", "training/reports/metrics/evaluate_dense_validation.json",
    "--error-samples", "0",
    "--seed", SEED,
)
run(
    "training/scripts/quantize_int8.py",
    "--input-model", "training/artifacts/student/sms_bytecnn_fp32.keras",
    "--output-tflite", "training/artifacts/student/sms_bytecnn_dense_int8.tflite",
    "--report", "training/reports/metrics/quantize_dense.json",
    "--profile", "formal",
    "--seed", SEED,
)

# 4) Strict prune (may fail closed) then formal quantize if pruned model exists.
pruned_keras = student_dir / "sms_bytecnn_pruned.keras"
final_tflite = student_dir / "sms_bytecnn_int8.tflite"
dense_tflite = student_dir / "sms_bytecnn_dense_int8.tflite"
prune_cmd = [
    sys.executable,
    "training/scripts/prune_channels.py",
    "--seed", SEED,
    "--student-config", str(cfg),
    "--distill-finetune",
]
print("RUN", " ".join(prune_cmd), flush=True)
prune_rc = subprocess.run(prune_cmd).returncode
prune_ok = prune_rc == 0 and pruned_keras.is_file()
print("PRUNE_OK", prune_ok, "rc", prune_rc, flush=True)

if prune_ok:
    run(
        "training/scripts/quantize_int8.py",
        "--input-model", "training/artifacts/student/sms_bytecnn_pruned.keras",
        "--output-tflite", "training/artifacts/student/sms_bytecnn_int8.tflite",
        "--report", "training/reports/metrics/quantize.json",
        "--profile", "formal",
        "--seed", SEED,
    )
    verify_rc = run(
        "training/scripts/verify_tflite.py",
        "--keras", "training/artifacts/student/sms_bytecnn_pruned.keras",
        "--tflite", "training/artifacts/student/sms_bytecnn_int8.tflite",
        "--quant-report", "training/reports/metrics/quantize.json",
        "--test", "training/data/processed/validation.jsonl",
        "--seed", SEED,
        allow_fail=True,
    )
    selected_tflite = "training/artifacts/student/sms_bytecnn_int8.tflite"
    selected_kind = "pruned_int8"
else:
    # Prefer Dense Full-INT8 when prune budgets are not met (pipeline v2 rule).
    if dense_tflite.is_file():
        shutil.copy2(dense_tflite, final_tflite)
    verify_rc = run(
        "training/scripts/verify_tflite.py",
        "--keras", "training/artifacts/student/sms_bytecnn_fp32.keras",
        "--tflite", "training/artifacts/student/sms_bytecnn_dense_int8.tflite",
        "--quant-report", "training/reports/metrics/quantize_dense.json",
        "--test", "training/data/processed/validation.jsonl",
        "--seed", SEED,
        allow_fail=True,
    )
    selected_tflite = "training/artifacts/student/sms_bytecnn_dense_int8.tflite"
    selected_kind = "dense_int8"

print("SELECTED_MODEL", selected_kind, selected_tflite, "verify_rc", verify_rc, flush=True)
Path("training/reports/metrics/selected_model.json").write_text(
    json.dumps(
        {
            "kind": selected_kind,
            "tflite": selected_tflite,
            "prune_ok": prune_ok,
            "verify_rc": verify_rc,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

run(
    "training/scripts/evaluate_pipeline_stages.py",
    "--split", "training/data/processed/validation.jsonl",
    "--dense-keras", "training/artifacts/student/sms_bytecnn_fp32.keras",
    "--pruned-keras", "training/artifacts/student/sms_bytecnn_pruned.keras",
    "--tflite", selected_tflite,
    "--output", "training/reports/metrics/stage_comparison_validation.json",
    "--seed", SEED,
)
run(
    "training/scripts/evaluate.py",
    "--mode", "tflite",
    "--tflite", selected_tflite,
    "--test", "training/data/processed/test.jsonl",
    "--stage", "final_locked_test",
    "--output", "training/reports/metrics/evaluate.json",
    "--error-samples", "40",
    "--error-output", "training/reports/metrics/error_samples.json",
    "--seed", SEED,
)
print("PIPELINE_OK", flush=True)

metrics_dir = ROOT / "training" / "reports" / "metrics"
for p in sorted(metrics_dir.glob("*.json")):
    print("METRIC_FILE", p.name, flush=True)
    data = json.loads(p.read_text(encoding="utf-8"))
    if p.name == "evaluate.json":
        print(json.dumps({
            "accuracy": data.get("metrics", {}).get("accuracy", data.get("accuracy")),
            "macro_f1": data.get("macro_f1"),
            "transaction_recall": data.get("transaction_recall"),
            "transaction_precision": data.get("transaction_precision"),
            "per_class": data.get("metrics", {}).get("per_class"),
            "test_count": data.get("test_count"),
            "evaluated_count": data.get("evaluated_count"),
            "claim_allowed": data.get("claim_allowed"),
        }, ensure_ascii=False, indent=2), flush=True)
    elif p.name == "student_distill.json":
        print({k: data.get(k) for k in ("macro_f1", "accuracy", "status") if k in data}, flush=True)

export_dir = Path("/content/colab_export_formal_v2")
if export_dir.exists():
    shutil.rmtree(export_dir)
(export_dir / "artifacts" / "student").mkdir(parents=True)
(export_dir / "artifacts" / "teacher").mkdir(parents=True)
for name in [
    "sms_bytecnn_int8.tflite",
    "sms_bytecnn_dense_int8.tflite",
    "sms_bytecnn_fp32.keras",
    "sms_bytecnn_pruned.keras",
    "distill_manifest.json",
]:
    src = student_dir / name
    if src.exists():
        shutil.copy2(src, export_dir / "artifacts" / "student" / name)
# teacher manifests + small metadata (not full BERT weights — too large)
for src in [
    ROOT / "training/data/manifests/teacher_logits_manifest.json",
    ROOT / "training/data/manifests/teacher_manifest.json",
]:
    if src.exists():
        shutil.copy2(src, export_dir / "artifacts" / "teacher" / src.name)
if metrics_dir.exists():
    shutil.copytree(metrics_dir, export_dir / "metrics", dirs_exist_ok=True)
shutil.make_archive("/content/colab_export_formal_v2", "zip", export_dir)
zip_size = Path("/content/colab_export_formal_v2.zip").stat().st_size
print("EXPORT_ZIP", zip_size, flush=True)
write_status("done", export_zip="/content/colab_export_formal_v2.zip", zip_size=zip_size)
PY

echo "=== upload pipeline script ==="
colab upload -s "$SESSION" "$OUT_DIR/run_pipeline.py" /content/run_pipeline_formal_v2.py

echo "=== detach pipeline on remote VM (survives local network blips) ==="
# start_new_session=True: job keeps running on Colab even after this short exec returns.
# NOTE: Colab still needs occasional keep-alive from this PC; do not sleep the machine for hours.
colab exec -s "$SESSION" --timeout 180 <<'EOF' | tee "$OUT_DIR/detach.txt"
import os, signal, subprocess, time
from pathlib import Path

script = Path("/content/run_pipeline_formal_v2.py")
log = Path("/content/formal_v2_job.log")
pid_path = Path("/content/formal_v2_job.pid")
status = Path("/content/formal_v2_status.json")

# Stop a previous detached run if still alive.
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

echo "=== poll status (tolerant of local disconnects) ==="
# Poll up to ~5h; each poll is a short exec. Network failures just retry.
deadline=$((SECONDS + 18000))
state="unknown"
while (( SECONDS < deadline )); do
  if timeout 90 colab exec -s "$SESSION" --timeout 60 <<'EOF' >"$OUT_DIR/poll_last.txt" 2>"$OUT_DIR/poll_err.txt"
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
    tail -n 30 "$OUT_DIR/poll_last.txt"
    if grep -qE '"stage": "?done"?' "$OUT_DIR/poll_last.txt"; then
      state="done"
      break
    fi
    if grep -qE '"stage": "?failed"?' "$OUT_DIR/poll_last.txt"; then
      state="failed"
      break
    fi
    # Job process died without writing done/failed.
    if grep -q 'PID_ALIVE False' "$OUT_DIR/poll_last.txt"; then
      if ! grep -qE '"stage": "?(done|failed|launching)"?' "$OUT_DIR/poll_last.txt"; then
        echo "DETACHED_PROCESS_DEAD" | tee -a "$OUT_DIR/pipeline.log"
        state="dead"
        break
      fi
      # failed status already handled above; if launching with dead pid, wait one more round
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
  if colab download -s "$SESSION" /content/colab_export_formal_v2.zip "$OUT_DIR/colab_export_formal_v2.zip" 2>&1 | tee "$OUT_DIR/download.log"; then
    break
  fi
  echo "DOWNLOAD_RETRY $attempt"
  sleep 30
done
test -f "$OUT_DIR/colab_export_formal_v2.zip"

python3 - <<'PY'
from pathlib import Path
import shutil
outs = sorted(Path.home().glob("colab_formal_v2_*/colab_export_formal_v2.zip"))
assert outs, "no export zip"
z = outs[-1]
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
