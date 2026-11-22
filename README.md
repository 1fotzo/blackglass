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

## Phase 1

On Parrot, from the clone:

```bash
blackglass lab test
blackglass corpus score
```

`lab test` runs the local lending pair. It records a reproduced finding only when the vulnerable pool breaks solvency and the patched pool holds. `corpus score` lists the public lending cases. Those stay inconclusive until a pinned run exists. The command exits non-zero if a patched twin fails.

## Phase 2

```bash
blackglass project create lending
blackglass project scope --path lab/lending
blackglass project import campaigns/lab-lending-solvency/result.json
blackglass report generate
```

Import refuses a path that is not in scope. The report has three sections: Reproduced, Hypotheses, and Recommendations. A campaign is listed as reproduced only when the vulnerable result broke, the patched result held, and the minimized test was hashed into evidence. Put RPC URLs and keys in the environment, not in `blackglass.toml`.

## Phase 3

Grant the address first. Put the indexer key in `.env` in the clone. That file is not committed. A shell variable with the same name wins over the file.

```bash
export BLACKGLASS_ETHERSCAN_API_KEY=your-key
blackglass project scope --chain-id 1 --address 0x0000000000000000000000000000000000000001
blackglass recon map --chain-id 1 --address 0x0000000000000000000000000000000000000001 --block 19000000
blackglass wallet inspect --chain-id 1 --address 0x0000000000000000000000000000000000000001 --block 19000000
blackglass report generate
```

`recon map` records what the address is, who can pull its assets, and which contracts it names. `wallet inspect` records the exposure only. Both are observations. An unlimited approval is not marked reproduced. Discovered neighbors are not added to scope. The window defaults to 5000 blocks and cannot exceed 100000.

## What the smoke test is

`lab/smoke` is a Foundry project with one contract. `forge test --root lab/smoke` compiles it and runs `test_ping`. `scripts/smoke-anvil.sh` starts Anvil, checks that the chain id is `31337`, and stops it.

## Continuous integration

`.github/workflows/ci.yml` builds `blackglass-lab` and runs pytest, the Foundry test, and the Anvil smoke check inside that image.
