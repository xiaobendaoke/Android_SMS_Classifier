#!/usr/bin/env bash
# Generate Software Bill of Materials (Phase 0 stub).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${ROOT}/reports/audit/dependency_sbom.json"

usage() {
  cat <<'EOF'
Usage: generate_sbom.sh [--help]

Generate dependency SBOM for release audit (Phase 0 stub).
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

mkdir -p "$(dirname "${OUTPUT}")"
cat > "${OUTPUT}" <<EOF
{
  "version": "0.1.0",
  "phase": 0,
  "note": "SBOM placeholder — populate during release audit",
  "components": []
}
EOF
echo "Wrote ${OUTPUT}"
exit 0
