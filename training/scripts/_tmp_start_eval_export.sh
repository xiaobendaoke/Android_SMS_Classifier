#!/usr/bin/env bash
set -eu
SCRIPT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/scripts/_tmp_launch_eval_export.sh"
sed -i 's/\r$//' "$SCRIPT"
LOG="$HOME/formal_v2_eval_export.log"
nohup bash "$SCRIPT" >"$LOG" 2>&1 &
echo $! >"$HOME/formal_v2_local_rerun.pid"
echo "PID=$(cat "$HOME/formal_v2_local_rerun.pid") log=$LOG"
sleep 10
head -n 40 "$LOG" || true
