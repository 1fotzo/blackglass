# BLACKGLASS

Web3 security confirmation engine. Phase 0 is the toolchain: the command line, the glass-plate banner, a Foundry smoke test, and a Linux lab image.

The lab image is the fuzzer host. The CLI runs on Windows and calls that image. Parrot OS can use the image or install the same tools directly.

## Install the CLI

Python 3.12 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
blackglass version
```

`blackglass` and `blackglass version` draw the glass plate in a terminal. `--quiet`, a pipe, `NO_COLOR`, or a terminal under 72 columns prints:

```text
BLACKGLASS  ·  web3 security
```

The right side of the plate reads `LAB READY` when the local Docker image is named `blackglass-lab`. Otherwise it reads `LAB ABSENT`.

## Lab image

The image contains Forge, Anvil, Cast, Medusa 1.5.1, and Slither. Halmos is left out unless you ask for it.

Windows, with Docker Desktop or Docker inside WSL2:

```powershell
docker build -t blackglass-lab -f docker/Dockerfile .
docker run --rm -v ${PWD}:/work -w /work -e PYTHONPATH=/work/src blackglass-lab bash -lc "pytest && forge test --root lab/smoke && bash scripts/smoke-anvil.sh"
```

Optional Halmos:

```powershell
docker build -t blackglass-lab -f docker/Dockerfile --build-arg INSTALL_HALMOS=1 .
```

Parrot, or any Debian-family Linux, can build that same image. To install the tools on the host instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

curl -L https://foundry.paradigm.xyz | bash
# open a new shell, or: source ~/.bashrc
foundryup

curl -fsSL -o /tmp/medusa.tar.gz \
  https://github.com/crytic/medusa/releases/download/v1.5.1/medusa-linux-x64.tar.gz
mkdir -p /tmp/medusa && tar -xzf /tmp/medusa.tar.gz -C /tmp/medusa
sudo install -m 0755 "$(find /tmp/medusa -type f -name medusa | head -n 1)" /usr/local/bin/medusa

pip install slither-analyzer
solc-select install 0.8.24
solc-select use 0.8.24

pytest
forge test --root lab/smoke
bash scripts/smoke-anvil.sh
```

A native Parrot install does not create the Docker image, so the banner stays `LAB ABSENT` until `blackglass-lab` exists locally.

## What the smoke test is

`lab/smoke` is a Foundry project with one contract. `forge test --root lab/smoke` compiles it and runs `test_ping`. `scripts/smoke-anvil.sh` starts Anvil, checks that the chain id is `31337`, and stops it.

## Continuous integration

`.github/workflows/ci.yml` builds `blackglass-lab` and runs pytest, the Foundry test, and the Anvil smoke check inside that image.
