# Docker Hub 在部分国内服务器上不可达，使用与现有项目一致的华为云镜像。
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_DEFAULT_INDEX=https://repo.huaweicloud.com/repository/pypi/simple

RUN pip install --no-cache-dir \
    --index-url https://repo.huaweicloud.com/repository/pypi/simple \
    uv==0.13.5

WORKDIR /app

# 先安装第三方依赖，源码变化时仍能复用 Docker 层缓存。
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY lector ./lector
RUN uv sync --frozen --no-dev

FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    LECTOR_DATA_DIR=/data \
    LECTOR_HOST=0.0.0.0 \
    LECTOR_PORT=8010 \
    LECTOR_BASE_PATH=/book

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY lector ./lector
COPY web ./web

RUN mkdir -p /data

EXPOSE 8010

CMD ["lector-server"]
