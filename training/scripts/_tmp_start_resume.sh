#!/usr/bin/env bash
set -eu
SCRIPT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/scripts/_tmp_launch_resume_after_distill.sh"
sed -i 's/\r$//' "$SCRIPT"
sed -i 's/\r$//' "/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/scripts/_tmp_restore_missing.sh"
LOG="$HOME/formal_v2_resume_launch.log"
nohup bash "$SCRIPT" >"$LOG" 2>&1 &
echo $! >"$HOME/formal_v2_local_rerun.pid"
echo "RESUME_LAUNCH_PID=$(cat "$HOME/formal_v2_local_rerun.pid") log=$LOG"
sleep 8
head -n 60 "$LOG" || true
