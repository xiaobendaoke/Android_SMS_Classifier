#!/usr/bin/env bash
set -euo pipefail

ROOT="/mnt/c/dev/Android_SMS_Classifier"
VENV="/home/colab/projects/Android_SMS_Classifier/.venv"
MODEL_DIR="${MODEL_DIR:-/home/colab/hf_cache/bert-base-chinese}"
PROXY="${HTTP_PROXY:-http://172.31.240.1:7897}"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "WSL training environment missing: $VENV" >&2
  exit 1
fi

export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$ROOT/training"
export TF_CPP_MIN_LOG_LEVEL="${TF_CPP_MIN_LOG_LEVEL:-2}"
export TOKENIZERS_PARALLELISM=false
export HF_HUB_DISABLE_XET=1

# Overseas fallbacks still use proxy; ModelScope domestic downloads use --noproxy.
export HTTP_PROXY="$PROXY" HTTPS_PROXY="$PROXY"
export http_proxy="$PROXY" https_proxy="$PROXY"

# ModelScope 【非官方】 API (AI-ModelScope/bert-base-chinese)
MS_API="https://www.modelscope.cn/api/v1/models/AI-ModelScope/bert-base-chinese/repo?Revision=master&FilePath="
HF_MIRROR="https://hf-mirror.com/google-bert/bert-base-chinese/resolve/main"
OFFICIAL="https://huggingface.co/google-bert/bert-base-chinese/resolve/main"

download_file() {
  local output="$1"
  local url="$2"
  local use_proxy="${3:-0}"
  if [[ -s "$MODEL_DIR/$output" ]]; then
    return 0
  fi
  rm -f "$MODEL_DIR/$output.part"
  echo "Downloading $output"
  echo "  url=$url proxy=$use_proxy"
  local -a curl_args=(
    -L --fail --retry 6 --retry-delay 3 --connect-timeout 30
    --max-time 0 -C -
    -o "$MODEL_DIR/$output.part"
  )
  if [[ "$use_proxy" == "1" ]]; then
    curl_args+=(--proxy "$PROXY")
  else
    curl_args+=(--noproxy '*')
  fi
  curl "${curl_args[@]}" "$url"
  mv -f "$MODEL_DIR/$output.part" "$MODEL_DIR/$output"
}

if [[ ! -s "$MODEL_DIR/model.safetensors" && ! -s "$MODEL_DIR/pytorch_model.bin" ]]; then
  mkdir -p "$MODEL_DIR"
  echo "Using ModelScope domestic mirror 【非官方】 (direct, no proxy)"
  echo "Source: AI-ModelScope/bert-base-chinese"

  for file in config.json tokenizer_config.json vocab.txt tokenizer.json; do
    download_file "$file" "${MS_API}${file}" 0 ||
      download_file "$file" "$HF_MIRROR/$file" 0 ||
      download_file "$file" "$OFFICIAL/$file" 1 ||
      true
  done
  if [[ ! -s "$MODEL_DIR/vocab.txt" || ! -s "$MODEL_DIR/config.json" ]]; then
    echo "Missing tokenizer/config after downloads." >&2
    exit 2
  fi

  # Prefer pytorch_model.bin from ModelScope; fall back to safetensors mirrors.
  if ! download_file "pytorch_model.bin" "${MS_API}pytorch_model.bin" 0; then
    echo "ModelScope weight download failed; trying hf-mirror 【非官方】" >&2
    download_file "model.safetensors" "$HF_MIRROR/model.safetensors" 0 ||
      download_file "model.safetensors" "$OFFICIAL/model.safetensors" 1
  fi

  weight=""
  if [[ -s "$MODEL_DIR/pytorch_model.bin" ]]; then
    weight="$MODEL_DIR/pytorch_model.bin"
  elif [[ -s "$MODEL_DIR/model.safetensors" ]]; then
    weight="$MODEL_DIR/model.safetensors"
  fi
  if [[ -z "$weight" || $(stat -c %s "$weight") -lt 300000000 ]]; then
    echo "Downloaded weight file is missing or unexpectedly small." >&2
    exit 2
  fi
  echo "Weight ready: $weight ($(stat -c %s "$weight") bytes)"
fi

echo "Using Chinese teacher at $MODEL_DIR"
cd "$ROOT"
exec "$VENV/bin/python" -u training/scripts/run_recall_v4.py \
  --teacher-model-path "$MODEL_DIR" \
  --run-name recall_v5 \
  --seed 42
