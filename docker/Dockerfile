### === Build stage === ###
FROM python:3.13-slim AS builder

ARG UV_DEFAULT_INDEX=https://pypi.org/simple \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    GITHUB_PROXY=""

ENV UV_DEFAULT_INDEX=${UV_DEFAULT_INDEX} \
    PYTHONDONTWRITEBYTECODE=${PYTHONDONTWRITEBYTECODE} \
    PIP_NO_CACHE_DIR=${PIP_NO_CACHE_DIR}

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src

RUN apt-get update -y && \
    apt-get install -y curl aria2

RUN --mount=type=cache,target=/root/.cache/uv \
    uv lock --no-upgrade && \
    uv sync --locked --no-install-project --no-editable && \
    uv pip install .

RUN <<EOF
M3U8_VERSION=$(curl -sL "${GITHUB_PROXY}https://api.github.com/repos/forkdo/m3u8-downloader/releases/latest" | grep '"tag_name":' | cut -d'"' -f4)
echo "Version: $M3U8_VERSION"
ARCH=$(uname -m)
case "$ARCH" in
    x86_64) ARCH="x86_64" ;;
    aarch64) ARCH="arm64" ;;
    armv7l) ARCH="armv7" ;;
    *) echo "Unsupported architecture: $ARCH" && exit 1 ;;
esac
curl -fSL -o m3u8-downloader.tar.gz "${GITHUB_PROXY}https://github.com/forkdo/m3u8-downloader/releases/download/${M3U8_VERSION}/m3u8-downloader_Linux_${ARCH}.tar.gz"
tar -xzf m3u8-downloader.tar.gz
EOF

### === Runtime stage === ###
FROM python:3.13-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH"

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/m3u8-downloader /usr/local/bin/m3u8-downloader
COPY --from=builder --chown=app:app /usr/bin/aria2c /usr/local/bin/

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends aria2 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
    
CMD ["fetcher"]