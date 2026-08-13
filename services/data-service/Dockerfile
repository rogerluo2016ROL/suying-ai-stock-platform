FROM node:20-slim AS lark-cli
ARG APT_MIRROR=deb.debian.org
# deb.debian.org 国内拉取极慢时可传 --build-arg APT_MIRROR=mirrors.aliyun.com
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && npm install -g @larksuite/cli@1.0.69 \
    && rm -rf /var/lib/apt/lists/*

FROM suying-python-base:latest

# 本阶段仍需 APT_MIRROR：chromium/tzdata 额外系统依赖（gcc/g++ 已含在基础镜像）
ARG APT_MIRROR=deb.debian.org

# System deps: tzdata for cron 时区; chromium + fonts-noto-cjk 用于早报海报
# SVG → PNG 渲染 (generate_poster_image)。gcc/g++ 已由基础镜像提供。
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    tzdata chromium fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
ENV CHROME_BIN=/usr/bin/chromium

# 从独立 Node 阶段复制飞书 CLI，避免在运行镜像安装完整 npm 工具链。
COPY --from=lark-cli /usr/local/bin/node /usr/local/bin/node
COPY --from=lark-cli /usr/local/lib/node_modules/@larksuite/cli /usr/local/lib/node_modules/@larksuite/cli
RUN ln -s /usr/local/lib/node_modules/@larksuite/cli/scripts/run.js /usr/local/bin/lark-cli

# kronos-data 包 (带 tushare/akshare/mootdx/pandas/numpy, 含 etl._get_etl_db PG 适配)
COPY packages/kronos-data /app/packages/kronos-data
RUN pip install --no-cache-dir /app/packages/kronos-data

COPY packages/kronos-auth /app/packages/kronos-auth
RUN pip install --no-cache-dir /app/packages/kronos-auth

# 定时研究流水线依赖
COPY packages/kronos-factors /app/packages/kronos-factors
RUN pip install --no-cache-dir /app/packages/kronos-factors
RUN pip install --no-cache-dir openai SQLAlchemy asyncpg tenacity

# data-service 直接依赖 (data-service 非 pip 包, 显式安装)
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" psycopg2-binary redis

# 保留仓库相对目录，定时任务可调用统一流水线和 screener 模型。
COPY services/data-service /app/services/data-service
COPY services/screener-service /app/services/screener-service
COPY tools /app/tools
COPY configs /app/configs
WORKDIR /app/services/data-service

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
