# 共享 Python 基础镜像 — 速赢AI 各微服务统一基线
# 构建（在仓库根，context=.. 以访问 packages/kronos-contracts）：
#   cd docker && bash build-base.sh
#   或: docker build -f base/Dockerfile -t suying-python-base:latest ..
FROM python:3.11-slim

ARG APT_MIRROR=deb.debian.org
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_DEFAULT_TIMEOUT=60
ENV PIP_INDEX_URL=$PIP_INDEX_URL PIP_DEFAULT_TIMEOUT=$PIP_DEFAULT_TIMEOUT

WORKDIR /app

# 系统编译依赖 (psycopg2/LightGBM/CatBoost 等需 gcc/g++)
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

# 共享健康契约包 (kronos_contracts — /api/v1/health[/live|/ready])
COPY packages/kronos-contracts /app/packages/kronos-contracts
RUN pip install --no-cache-dir /app/packages/kronos-contracts
