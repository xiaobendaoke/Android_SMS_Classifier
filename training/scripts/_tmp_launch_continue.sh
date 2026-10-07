#!/usr/bin/env bash
set -eu
export PATH="/home/colab/.local/bin:/usr/bin:/bin"
SCRIPT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/scripts/_tmp_continue_formal_v2.sh"
sed -i 's/\r$//' "$SCRIPT"
LOG="$HOME/formal_v2_continue_$(date +%Y%m%d_%H%M%S).log"
PIDFILE="$HOME/formal_v2_local_rerun.pid"
nohup bash "$SCRIPT" >"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "LAUNCHED pid=$(cat "$PIDFILE") log=$LOG"
sleep 5
head -n 50 "$LOG" || true
