#!/usr/bin/env bash
# Emit a wake tick every 3 minutes for the agent monitor loop.
set -eu
export PATH="/home/colab/.local/bin:/usr/bin:/bin"
while true; do
  sleep 180
  echo 'AGENT_LOOP_TICK_formal_v2 {"prompt":"检查 formal v2 Colab 进度：读 remote status + continue log 尾部；若 stage/阶段有变化或 done/failed/zip 已落地则向用户简要汇报；否则只记内部状态并继续等下一 tick。完成后拷贝确认 Windows zip。"}'
done
