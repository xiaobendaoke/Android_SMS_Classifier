#!/usr/bin/env bash
set -euo pipefail
PROXY="${HTTP_PROXY:-http://172.31.240.1:7897}"
URLS=(
  "https://www.modelscope.cn/api/v1/models/tiansz/bert-base-chinese/repo?Revision=master&FilePath=pytorch_model.bin"
  "https://www.modelscope.cn/api/v1/models/AI-ModelScope/bert-base-chinese/repo?Revision=master&FilePath=pytorch_model.bin"
  "https://www.modelscope.cn/models/tiansz/bert-base-chinese/resolve/master/pytorch_model.bin"
  "https://hf-mirror.com/google-bert/bert-base-chinese/resolve/main/model.safetensors"
)
for url in "${URLS[@]}"; do
  echo "=== DIRECT $url"
  curl -s -o /dev/null -w "http=%{http_code} speed=%{speed_download} size=%{size_download} time=%{time_total}\n" \
    --noproxy '*' --max-time 12 --range 0-1048575 -L "$url" || echo FAIL
  echo "=== PROXY $url"
  curl -s -o /dev/null -w "http=%{http_code} speed=%{speed_download} size=%{size_download} time=%{time_total}\n" \
    --proxy "$PROXY" --max-time 12 --range 0-1048575 -L "$url" || echo FAIL
done
