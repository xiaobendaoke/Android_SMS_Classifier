#!/usr/bin/env bash
# Download bert-base-multilingual-cased via host proxy, then train teacher offline.
set -euo pipefail

PROXY="${HTTP_PROXY:-http://172.31.240.1:7897}"
HF_HOME="${HF_HOME:-/home/colab/hf_cache}"
MODEL_DIR="${MODEL_DIR:-$HF_HOME/bert-base-multilingual-cased}"
REPO="https://huggingface.co/google-bert/bert-base-multilingual-cased/resolve/main"
ROOT="/home/colab/projects/Android_SMS_Classifier"
PY="${ROOT}/.venv/bin/python"
WIN_TRAIN="/mnt/c/dev/Android_SMS_Classifier/training"

export HTTP_PROXY="$PROXY"
export HTTPS_PROXY="$PROXY"
export http_proxy="$PROXY"
export https_proxy="$PROXY"
export HF_HOME
export HF_HUB_DISABLE_XET=1
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="/mnt/c/dev/Android_SMS_Classifier/training"

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

echo "PROXY=$PROXY"
echo "MODEL_DIR=$MODEL_DIR"

download_required() {
  local name="$1"
  local url="$REPO/$name"
  if [[ -s "$name" ]]; then
    echo "SKIP $name (exists $(du -h "$name" | cut -f1))"
    return 0
  fi
  echo "DOWNLOAD $name"
  curl -L --fail --retry 5 --retry-delay 2 \
    --connect-timeout 30 --max-time 0 \
    --proxy "$PROXY" \
    -C - \
    -o "$name.part" \
    "$url"
  mv -f "$name.part" "$name"
  echo "OK $name ($(du -h "$name" | cut -f1))"
}

download_optional() {
  local name="$1"
  local url="$REPO/$name"
  if [[ -s "$name" ]]; then
    echo "SKIP $name (exists)"
    return 0
  fi
  echo "DOWNLOAD_OPTIONAL $name"
  if curl -L --fail --retry 2 --retry-delay 1 \
    --connect-timeout 20 --max-time 120 \
    --proxy "$PROXY" \
    -o "$name.part" \
    "$url"; then
    mv -f "$name.part" "$name"
    echo "OK $name"
  else
    rm -f "$name.part"
    echo "SKIP_OPTIONAL $name (not available)"
  fi
}

# Required small files.
for f in config.json tokenizer_config.json tokenizer.json vocab.txt; do
  download_required "$f"
done
download_optional special_tokens_map.json

# ~681MB weights
download_required model.safetensors

echo "=== MODEL_DIR listing ==="
ls -lh "$MODEL_DIR"

echo "=== Start teacher offline ==="
exec "$PY" -u "$WIN_TRAIN/scripts/train_teacher.py" \
  --config "$WIN_TRAIN/configs/teacher.yaml" \
  --model-path "$MODEL_DIR" \
  --seed 42
