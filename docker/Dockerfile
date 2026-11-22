# BLACKGLASS lab image.
# Default tools: Forge, Anvil, Cast, Medusa, Slither.
# Halmos stays optional: docker build --build-arg INSTALL_HALMOS=1
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FOUNDRY_DIR=/opt/foundry \
    PATH="/opt/foundry/bin:${PATH}" \
    MEDUSA_VERSION=1.5.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        findutils \
        git \
        tar \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://foundry.paradigm.xyz | bash \
    && foundryup

RUN curl -fsSL -o /tmp/medusa.tar.gz \
        "https://github.com/crytic/medusa/releases/download/v${MEDUSA_VERSION}/medusa-linux-x64.tar.gz" \
    && mkdir -p /tmp/medusa \
    && tar -xzf /tmp/medusa.tar.gz -C /tmp/medusa \
    && install -m 0755 "$(find /tmp/medusa -type f -name medusa | head -n 1)" /usr/local/bin/medusa \
    && rm -rf /tmp/medusa /tmp/medusa.tar.gz

RUN pip install --no-cache-dir \
        "pydantic>=2" \
        "pytest>=8" \
        "rich>=13" \
        "slither-analyzer" \
        "typer>=0.12" \
    && solc-select install 0.8.24 \
    && solc-select use 0.8.24

ARG INSTALL_HALMOS=0
RUN if [ "$INSTALL_HALMOS" = "1" ]; then pip install --no-cache-dir halmos; fi

RUN forge --version \
    && anvil --version \
    && cast --version \
    && (medusa version || medusa --version) \
    && slither --version

WORKDIR /work
CMD ["bash"]
