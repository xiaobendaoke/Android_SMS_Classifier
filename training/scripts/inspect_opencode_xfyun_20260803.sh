#!/usr/bin/env bash
set -euo pipefail

timeout 30 bash -ic 'opencode --help'
printf '%s\n' '--- models ---'
timeout 30 bash -ic 'opencode models' || true
