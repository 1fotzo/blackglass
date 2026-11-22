#!/usr/bin/env bash
# Start Anvil, confirm the local chain id, then stop it.
set -euo pipefail

port="${ANVIL_PORT:-8545}"
anvil --port "$port" --silent &
pid=$!
cleanup() {
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
trap cleanup EXIT

rpc="http://127.0.0.1:${port}"
ready=0
for _ in $(seq 1 50); do
  if cast chain-id --rpc-url "$rpc" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.1
done

if [[ "$ready" -ne 1 ]]; then
  echo "anvil did not start" >&2
  exit 1
fi

chain_id="$(cast chain-id --rpc-url "$rpc")"
if [[ "$chain_id" != "31337" ]]; then
  echo "unexpected chain id: ${chain_id}" >&2
  exit 1
fi

echo "anvil smoke ok chain_id=${chain_id}"
