#!/usr/bin/env bash
# Parrot OS entrypoint. Same installer as bash install.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "${ROOT}/scripts/install-linux.sh"
