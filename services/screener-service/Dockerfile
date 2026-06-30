FROM python:3.11-slim
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_DEFAULT_TIMEOUT=60
ENV PIP_INDEX_URL=$PIP_INDEX_URL PIP_DEFAULT_TIMEOUT=$PIP_DEFAULT_TIMEOUT

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

# Copy and install packages actually used by screener-service.
COPY packages/kronos-factors /app/packages/kronos-factors
RUN pip install --no-cache-dir /app/packages/kronos-factors

# Copy service
COPY services/screener-service /app/service
RUN pip install --no-cache-dir /app/service

# Expose port
EXPOSE 8001

# Run
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
