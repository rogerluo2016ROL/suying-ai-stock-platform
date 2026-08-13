#!/usr/bin/env bash
# 构建共享 Python 基础镜像 suying-python-base:latest
# 各微服务 Dockerfile 均 FROM 此镜像；改基础镜像后须先跑本脚本再 compose build。
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> 构建 suying-python-base:latest (context=仓库根)"
docker build -f docker/base/Dockerfile -t suying-python-base:latest \
    --build-arg APT_MIRROR="${APT_MIRROR:-deb.debian.org}" \
    --build-arg PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
    .

echo "==> 完成。现在可: cd docker && docker compose build"
