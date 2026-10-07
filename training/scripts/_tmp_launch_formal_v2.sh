#!/usr/bin/env bash
set -eu
export PATH="/home/colab/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
if [[ -f "$HOME/.config/wsl-proxy.env" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/wsl-proxy.env"
fi
echo "PROXY=${http_proxy:-none}"
WIN_SCRIPT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/scripts/_colab_distill_e10_run.sh"
sed -i 's/\r$//' "$WIN_SCRIPT"
cp -f "$WIN_SCRIPT" "$HOME/projects/Android_SMS_Classifier/training/scripts/_colab_distill_e10_run.sh"
LOG="$HOME/formal_v2_local_rerun_$(date +%Y%m%d_%H%M%S).log"
PIDFILE="$HOME/formal_v2_local_rerun.pid"
nohup bash "$HOME/projects/Android_SMS_Classifier/training/scripts/_colab_distill_e10_run.sh" >"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "LAUNCHED pid=$(cat "$PIDFILE") log=$LOG"
sleep 3
head -n 40 "$LOG" || true
