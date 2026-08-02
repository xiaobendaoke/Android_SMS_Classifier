#!/usr/bin/env bash
set -euo pipefail
export PATH="/home/colab/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
if [[ -f "$HOME/.config/wsl-proxy.env" ]]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/wsl-proxy.env"
fi
echo "PROXY=${http_proxy:-none}"
command -v colab
colab sessions || true
colab whoami || true
