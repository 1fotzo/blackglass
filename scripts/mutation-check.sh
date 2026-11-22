#!/usr/bin/env bash
# Copy the patched pool, delete the liability update, and require Forge to fail.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v forge >/dev/null 2>&1; then
  echo "forge is not on PATH" >&2
  exit 1
fi
tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

cp -a "${ROOT}/lab/lending/." "${tmp}/lending/"
python -c 'from pathlib import Path; import sys; p = Path(sys.argv[1]); text = p.read_text(encoding="utf-8");
assert "PATCH:" in text, "patch marker missing";
p.write_text("".join(line for line in text.splitlines(True) if "PATCH:" not in line), encoding="utf-8")' \
  "${tmp}/lending/src/PatchedPool.sol"

set +e
forge test --root "${tmp}/lending" --match-contract Patched
code=$?
set -e

if [[ "$code" -eq 0 ]]; then
  echo "mutation was not caught" >&2
  exit 1
fi
echo "mutation caught"
