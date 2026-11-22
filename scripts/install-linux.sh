#!/usr/bin/env bash
# Install BLACKGLASS and the Phase 0 lab tools on Parrot OS, or another
# Debian-family system. Run from a clone as your normal user:
#   bash install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MEDUSA_VERSION="1.5.1"
SOLC_VERSION="0.8.24"

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run this as your normal user. It uses sudo only for apt." >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot read /etc/os-release." >&2
  exit 1
fi
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}:${ID_LIKE:-}" in
  parrot:*|*:parrot*|debian:*|*:debian*|ubuntu:*|*:ubuntu*) ;;
  *)
    echo "This installer supports Parrot OS and other Debian-family systems. Detected: ${ID:-unknown}." >&2
    exit 1
    ;;
esac

if [[ "$(uname -m)" != "x86_64" ]]; then
  echo "The pinned Medusa binary is linux-x64. This machine is $(uname -m)." >&2
  exit 1
fi

echo "Installing system packages..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  python3 \
  python3-venv \
  python3-pip \
  curl \
  ca-certificates \
  git \
  tar \
  findutils

if apt-cache show python3.12 >/dev/null 2>&1; then
  sudo apt-get install -y python3.12 python3.12-venv || true
fi

PYTHON=""
for candidate in python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    PYTHON="$candidate"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "BLACKGLASS needs Python 3.12 or newer, and this system does not have it." >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]] \
  || ! .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  rm -rf .venv
  "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install slither-analyzer
solc-select install "$SOLC_VERSION"
solc-select use "$SOLC_VERSION"

export FOUNDRY_DIR="${FOUNDRY_DIR:-$HOME/.foundry}"
export PATH="${FOUNDRY_DIR}/bin:${HOME}/.local/bin:${PATH}"
if [[ ! -x "${FOUNDRY_DIR}/bin/foundryup" ]]; then
  echo "Downloading Foundry..."
  curl -fsSL https://foundry.paradigm.xyz | bash
fi
foundryup

echo "Installing Medusa ${MEDUSA_VERSION}..."
mkdir -p "${HOME}/.local/bin"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL -o "${tmp}/medusa.tar.gz" \
  "https://github.com/crytic/medusa/releases/download/v${MEDUSA_VERSION}/medusa-linux-x64.tar.gz"
tar -xzf "${tmp}/medusa.tar.gz" -C "$tmp"
install -m 0755 "$(find "$tmp" -type f -name medusa | head -n 1)" "${HOME}/.local/bin/medusa"

install_wrapper() {
  local name="$1"
  local target="${ROOT}/.venv/bin/${name}"
  if [[ ! -x "$target" ]]; then
    return 0
  fi
  cat > "${HOME}/.local/bin/${name}" <<EOF
#!/usr/bin/env bash
exec "${target}" "\$@"
EOF
  chmod 0755 "${HOME}/.local/bin/${name}"
}
install_wrapper blackglass
install_wrapper slither
install_wrapper solc-select
install_wrapper solc
hash -r

path_line='export PATH="$HOME/.foundry/bin:$HOME/.local/bin:$PATH"'
if ! grep -Fqs '.foundry/bin' "${HOME}/.bashrc"; then
  printf '\n# BLACKGLASS lab tools\n%s\n' "$path_line" >> "${HOME}/.bashrc"
fi

echo "Checking tools..."
forge --version
anvil --version
cast --version
medusa version || medusa --version
slither --version
blackglass version --quiet

echo "Running smoke tests..."
pytest
forge test --root lab/smoke
bash scripts/smoke-anvil.sh

echo
echo "BLACKGLASS is ready. Open a new terminal, then run: blackglass version"
