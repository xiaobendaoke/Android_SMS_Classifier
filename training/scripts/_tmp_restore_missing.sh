#!/usr/bin/env bash
set -eu
export PATH="/usr/bin:/bin"
ROOT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier"
cd "$ROOT"
git show 'stash@{0}^3:training/scripts/generate_representative_manifest.py' > training/scripts/generate_representative_manifest.py
git show 'stash@{0}^3:training/scripts/evaluate_pipeline_stages.py' > training/scripts/evaluate_pipeline_stages.py
python3 - <<'PY'
from pathlib import Path
for rel in (
    "training/scripts/generate_representative_manifest.py",
    "training/scripts/evaluate_pipeline_stages.py",
):
    p = Path(rel)
    data = p.read_bytes().lstrip(b"\xef\xbb\xbf")
    # normalize newlines to LF
    text = data.decode("utf-8").replace("\r\n", "\n")
    p.write_text(text, encoding="utf-8", newline="\n")
    print("OK", rel, p.stat().st_size)
PY
# also copy into WSL project
WSL_ROOT="$HOME/projects/Android_SMS_Classifier"
mkdir -p "$WSL_ROOT/training/scripts"
cp -f training/scripts/generate_representative_manifest.py "$WSL_ROOT/training/scripts/"
cp -f training/scripts/evaluate_pipeline_stages.py "$WSL_ROOT/training/scripts/"
echo COPIED_TO_WSL
