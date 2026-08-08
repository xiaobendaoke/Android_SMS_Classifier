from pathlib import Path
import os
import time

status = Path("/content/formal_v2_status.json")
log = Path("/content/formal_v2_job.log")
pid_path = Path("/content/formal_v2_job.pid")
print("NOW", time.strftime("%Y-%m-%d %H:%M:%S"))
print("STATUS_JSON", status.read_text(encoding="utf-8") if status.exists() else "MISSING")
print("PID_FILE", pid_path.read_text(encoding="utf-8").strip() if pid_path.exists() else "MISSING")
alive = False
pid = None
if pid_path.exists():
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)
        alive = True
    except Exception:
        alive = False
print("PID_ALIVE", alive)
if log.exists():
    text = log.read_text(encoding="utf-8", errors="replace")
    print("LOG_BYTES", len(text))
    print("LOG_TAIL")
    print(text[-2200:])
# Look for epoch markers
if log.exists():
    lines = [ln for ln in text.splitlines() if any(k in ln.lower() for k in ("epoch", "loss", "f1", "status", "run ", "wrote", "export", "macro"))]
    print("KEY_LINES", len(lines))
    for ln in lines[-15:]:
        print(ln)
# child processes
if pid and alive:
    try:
        children = Path(f"/proc/{pid}/task")
        print("PROC_OK", Path(f"/proc/{pid}/cmdline").read_bytes()[:200])
    except Exception as exc:
        print("PROC_ERR", type(exc).__name__, exc)
print("ZIP", Path("/content/colab_export_formal_v2.zip").exists())
print("TEACHER_CACHE", Path("/content/hf_cache/bert-base-multilingual-cased/config.json").exists())
for p in [
    "/content/Android_SMS_Classifier/training/artifacts/teacher",
    "/content/Android_SMS_Classifier/training/artifacts/student",
]:
    d = Path(p)
    if d.exists():
        files = sorted(x.name for x in d.rglob("*") if x.is_file())[:12]
        print("ART", p, "n=", len(list(d.rglob('*'))), "sample=", files)
