#!/usr/bin/env bash
# Probe BERT weight mirrors and pick the fastest, then resume download + train.
set -euo pipefail

PROXY="${HTTP_PROXY:-http://172.31.240.1:7897}"
HF_HOME="${HF_HOME:-/home/colab/hf_cache}"
MODEL_DIR="${MODEL_DIR:-$HF_HOME/bert-base-multilingual-cased}"
ROOT="/home/colab/projects/Android_SMS_Classifier"
PY="${ROOT}/.venv/bin/python"
WIN_TRAIN="/mnt/c/dev/Android_SMS_Classifier/training"

export HTTP_PROXY="$PROXY" HTTPS_PROXY="$PROXY" http_proxy="$PROXY" https_proxy="$PROXY"
export HF_HOME HF_HUB_DISABLE_XET=1 TOKENIZERS_PARALLELISM=false
export PYTHONPATH="/mnt/c/dev/Android_SMS_Classifier/training"

# Stop any previous curl/download for this file.
pkill -f 'model.safetensors' 2>/dev/null || true
pkill -f '_download_bert_via_proxy.sh' 2>/dev/null || true
sleep 1

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

probe() {
  local name="$1"
  local url="$2"
  local out
  out=$(curl -s -o /dev/null -w "%{http_code} %{speed_download} %{time_total} %{size_download}" \
    --proxy "$PROXY" --max-time 20 --range 0-2097151 -L "$url" || true)
  echo "PROBE $name -> $out  url=$url"
  # return speed as integer bytes/s (field 2)
  echo "$out" | awk '{print int($2+0)}'
}

echo "PROXY=$PROXY"
echo "MODEL_DIR=$MODEL_DIR"

# Candidate mirrors. hf-mirror / modelscope are unofficial third-party mirrors.
HF_OFFICIAL="https://huggingface.co/google-bert/bert-base-multilingual-cased/resolve/main/model.safetensors"
HF_MIRROR="https://hf-mirror.com/google-bert/bert-base-multilingual-cased/resolve/main/model.safetensors"
# ModelScope open download endpoint for same model id (unofficial relative to HF).
MS_URL="https://www.modelscope.cn/models/AI-ModelScope/bert-base-multilingual-cased/resolve/master/pytorch_model.bin"

speed_official=$(probe official "$HF_OFFICIAL" | tail -1)
speed_mirror=$(probe hf_mirror "$HF_MIRROR" | tail -1)
speed_ms=$(probe modelscope "$MS_URL" | tail -1)

echo "SPEEDS official=$speed_official mirror=$speed_mirror modelscope=$speed_ms"

best_name="hf_mirror"
best_url="$HF_MIRROR"
best_file="model.safetensors"
best_speed="$speed_mirror"

if [ "${speed_ms:-0}" -gt "${best_speed:-0}" ]; then
  best_name="modelscope"
  best_url="$MS_URL"
  best_file="pytorch_model.bin"
  best_speed="$speed_ms"
fi
if [ "${speed_official:-0}" -gt "${best_speed:-0}" ]; then
  best_name="official"
  best_url="$HF_OFFICIAL"
  best_file="model.safetensors"
  best_speed="$speed_official"
fi

echo "SELECTED mirror=$best_name speed=${best_speed}B/s file=$best_file"
echo "NOTE: hf-mirror / modelscope are 【非官方】 third-party mirrors of public BERT weights."

# Ensure small files exist (from previous official download or mirror).
ensure_small() {
  local name="$1"
  local base="$2"
  if [[ -s "$name" ]]; then
    echo "SKIP $name"
    return 0
  fi
  echo "DOWNLOAD $name from $base"
  curl -L --fail --retry 4 --retry-delay 2 --proxy "$PROXY" -C - -o "$name.part" "$base/$name"
  mv -f "$name.part" "$name"
}

SMALL_BASE="https://hf-mirror.com/google-bert/bert-base-multilingual-cased/resolve/main"
for f in config.json tokenizer_config.json tokenizer.json vocab.txt; do
  ensure_small "$f" "$SMALL_BASE" || ensure_small "$f" "https://huggingface.co/google-bert/bert-base-multilingual-cased/resolve/main"
done

# Remove incompatible partial if switching to pytorch_model.bin
if [[ "$best_file" == "pytorch_model.bin" ]]; then
  rm -f model.safetensors.part model.safetensors
elif [[ -s model.safetensors ]]; then
  echo "SKIP model.safetensors already complete"
else
  # Keep .part for resume if same file type
  :
fi

if [[ ! -s "$best_file" ]]; then
  echo "DOWNLOAD $best_file via $best_name"
  curl -L --fail --retry 8 --retry-delay 3 \
    --connect-timeout 30 --max-time 0 \
    --proxy "$PROXY" \
    -C - \
    -o "${best_file}.part" \
    "$best_url"
  mv -f "${best_file}.part" "$best_file"
fi

echo "OK $best_file ($(du -h "$best_file" | cut -f1))"
ls -lh "$MODEL_DIR"

echo "=== Start teacher offline ==="
exec "$PY" -u "$WIN_TRAIN/scripts/train_teacher.py" \
  --config "$WIN_TRAIN/configs/teacher.yaml" \
  --model-path "$MODEL_DIR" \
  --seed 42
