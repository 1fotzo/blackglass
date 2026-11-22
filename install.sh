#!/usr/bin/env bash
# One command after clone: bash install.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${ROOT}/scripts/install-linux.sh"
