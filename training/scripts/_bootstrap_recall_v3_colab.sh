#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$(find /mnt/c/Users/woshinibaba/Documents -maxdepth 4 -name '_colab_recall_v3_run.sh' 2>/dev/null | head -n 1)"
if [[ -z "$SCRIPT" ]]; then
  echo "FATAL: _colab_recall_v3_run.sh not found" >&2
  exit 1
fi
echo "FOUND $SCRIPT"
sed -i 's/\r$//' "$SCRIPT"
chmod +x "$SCRIPT"
cp "$SCRIPT" "$HOME/_colab_recall_v3_run.sh"
nohup bash "$HOME/_colab_recall_v3_run.sh" > "$HOME/colab_recall_v3_launch.log" 2>&1 &
echo "LAUNCH_PID $!"
sleep 4
tail -n 40 "$HOME/colab_recall_v3_launch.log"
