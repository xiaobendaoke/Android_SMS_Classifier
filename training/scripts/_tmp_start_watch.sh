#!/usr/bin/env bash
set -eu
SCRIPT="/mnt/c/Users/woshinibaba/Documents/oppo的项目/Android_SMS_Classifier/training/scripts/_tmp_watch_formal_done.sh"
sed -i 's/\r$//' "$SCRIPT"
nohup bash "$SCRIPT" >"$HOME/formal_v2_watch.log" 2>&1 &
echo $! >"$HOME/formal_v2_watch.pid"
echo "WATCH_PID=$(cat "$HOME/formal_v2_watch.pid")"
