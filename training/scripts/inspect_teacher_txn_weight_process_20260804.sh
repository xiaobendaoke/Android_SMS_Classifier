#!/usr/bin/env bash
set -euo pipefail
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
ps -eo pid,etime,pcpu,pmem,args | grep -E 'train_teacher|run_xfyun_overlay_teacher' | grep -v grep || true
