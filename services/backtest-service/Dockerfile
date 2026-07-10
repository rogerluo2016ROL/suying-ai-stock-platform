FROM python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_DEFAULT_TIMEOUT=60
ENV PIP_INDEX_URL=$PIP_INDEX_URL PIP_DEFAULT_TIMEOUT=$PIP_DEFAULT_TIMEOUT

WORKDIR /app
COPY packages/kronos-contracts /app/packages/kronos-contracts
RUN pip install --no-cache-dir /app/packages/kronos-contracts
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

COPY packages/kronos-factors /app/packages/kronos-factors
RUN pip install --no-cache-dir /app/packages/kronos-factors

COPY services/backtest-service /app/service
RUN pip install --no-cache-dir /app/service

EXPOSE 8007
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
