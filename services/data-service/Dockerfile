FROM python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_DEFAULT_TIMEOUT=60
ENV PIP_INDEX_URL=$PIP_INDEX_URL PIP_DEFAULT_TIMEOUT=$PIP_DEFAULT_TIMEOUT

WORKDIR /app
COPY packages/kronos-contracts /app/packages/kronos-contracts
RUN pip install --no-cache-dir /app/packages/kronos-contracts

# System deps: gcc/g++ for psycopg2 build, tzdata for cron 时区 (Asia/Shanghai)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ tzdata && rm -rf /var/lib/apt/lists/*

# kronos-data 包 (带 tushare/akshare/mootdx/pandas/numpy, 含 etl._get_etl_db PG 适配)
COPY packages/kronos-data /app/packages/kronos-data
RUN pip install --no-cache-dir /app/packages/kronos-data

# data-service 直接依赖 (data-service 非 pip 包, 显式安装)
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" psycopg2-binary redis

# data-service 源码 (非 pip 包, COPY 后设 WORKDIR 使 `app` 可 import)
COPY services/data-service /app/data-service
WORKDIR /app/data-service

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
