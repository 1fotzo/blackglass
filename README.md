# BLACKGLASS

Web3 security confirmation engine. Phase 0 is the toolchain: the command line, the glass-plate banner, a Foundry smoke test, and the lab tools.

## Install on Parrot OS

Clone the repo, then run one command as your normal user:

```bash
bash install.sh
```

That installs Python 3.12 when the distro has it, the BLACKGLASS command, Foundry, Medusa 1.5.1, Slither, and solc 0.8.24. It then runs the smoke tests. Open a new terminal and run `blackglass version`.

The same installer is `bash scripts/install-parrot.sh`. It also runs on other Debian-family systems. It refuses to run as root, and the Medusa binary it downloads is linux-x64.

`LAB READY` on the banner means Forge, Anvil, and Medusa are on `PATH`, or a Docker image named `blackglass-lab` is present.

## Install the CLI on Windows

Python 3.12 or newer. Windows runs the CLI. The lab tools run in the Linux image below.

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

The right side of the plate reads `LAB READY` when Forge, Anvil, and Medusa are on `PATH`, or when a Docker image named `blackglass-lab` is present. Otherwise it reads `LAB ABSENT`.

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

## What the smoke test is

`lab/smoke` is a Foundry project with one contract. `forge test --root lab/smoke` compiles it and runs `test_ping`. `scripts/smoke-anvil.sh` starts Anvil, checks that the chain id is `31337`, and stops it.

## Continuous integration

`.github/workflows/ci.yml` builds `blackglass-lab` and runs pytest, the Foundry test, and the Anvil smoke check inside that image.
