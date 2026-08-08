#!/usr/bin/env bash
set -eu
SCRIPT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/scripts/_tmp_loop_monitor.sh"
sed -i 's/\r$//' "$SCRIPT"
pkill -f '_tmp_loop_monitor.sh' 2>/dev/null || true
sleep 1
nohup bash "$SCRIPT" >"$HOME/formal_v2_loop_ticks.log" 2>&1 &
echo $! >"$HOME/formal_v2_loop.pid"
echo "LOOP_PID=$(cat "$HOME/formal_v2_loop.pid")"
