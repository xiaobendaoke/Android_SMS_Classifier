#!/usr/bin/env bash
set -u
echo "=== files ==="
ls -lh /home/colab/hf_cache/bert-base-multilingual-cased/ || true
echo "=== processes ==="
ps -eo pid,etime,pcpu,cmd | grep -E 'curl|train_teacher|_download_bert' | grep -v grep || true
echo "=== proxy probe ==="
curl -s -o /dev/null -w "proxy_hf http=%{http_code} time=%{time_total}s\n" \
  --proxy http://172.31.240.1:7897 --max-time 20 https://huggingface.co || echo "proxy_hf fail"
echo "=== direct probe ==="
curl -s -o /dev/null -w "direct_hf http=%{http_code} time=%{time_total}s\n" \
  --max-time 8 https://huggingface.co || echo "direct_hf fail"
echo "=== CDN via proxy (first 2MB of weights) ==="
# Resolve redirect then time a chunk download via proxy
URL=$(curl -sI -L --proxy http://172.31.240.1:7897 --max-time 30 \
  "https://huggingface.co/google-bert/bert-base-multilingual-cased/resolve/main/model.safetensors" \
  | awk 'BEGIN{IGNORECASE=1} /^location:/ {url=$2} END{gsub("\r","",url); print url}')
echo "cdn_url=${URL:0:120}..."
if [ -n "$URL" ]; then
  curl -s -o /dev/null -w "cdn_proxy http=%{http_code} speed=%{speed_download}B/s time=%{time_total}s size=%{size_download}\n" \
    --proxy http://172.31.240.1:7897 --max-time 25 --range 0-2097151 "$URL" || echo "cdn_proxy fail"
fi
