#!/usr/bin/env bash
set -eu
export PATH="/home/colab/.local/bin:/usr/bin:/bin"
source "$HOME/.config/wsl-proxy.env"
export NO_PROXY="localhost,127.0.0.1,::1,.prod.colab.dev"
export no_proxy="$NO_PROXY"
echo "PROXY=$http_proxy NO_PROXY=$NO_PROXY"
colab sessions
colab status -s sms_formal_v2
BUNDLE=/tmp/sms_formal_v2_bundle.tgz
ls -lh "$BUNDLE"
echo "UPLOAD with proxy+NO_PROXY prod.colab.dev"
if colab upload -s sms_formal_v2 "$BUNDLE" /content/sms_formal_v2_bundle.tgz; then
  echo UPLOAD_OK
else
  echo UPLOAD_FAIL_1
  echo "UPLOAD without proxy"
  env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY \
    colab upload -s sms_formal_v2 "$BUNDLE" /content/sms_formal_v2_bundle.tgz && echo UPLOAD_OK || echo UPLOAD_FAIL_2
fi
