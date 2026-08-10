FROM python:3.11-slim
ARG APT_MIRROR=deb.debian.org
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_DEFAULT_TIMEOUT=60
ENV PIP_INDEX_URL=$PIP_INDEX_URL PIP_DEFAULT_TIMEOUT=$PIP_DEFAULT_TIMEOUT

WORKDIR /app
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

# Copy backend
COPY backend /app/backend

# kronos-contracts 共享包 (health 契约, /api/v1/health/ready 依赖)
COPY packages/kronos-contracts /app/packages/kronos-contracts
RUN pip install --no-cache-dir /app/packages/kronos-contracts

# Install backend dependencies (单一来源: backend/requirements.txt)
RUN pip install --no-cache-dir -r backend/requirements.txt

EXPOSE 9001
# AC-8: alembic upgrade head runs inside main.py lifespan (covers docker compose +
# manual `uvicorn` start uniformly), so the Dockerfile just boots uvicorn in the
# backend/ workdir where `app.main` is importable.
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9001"]
