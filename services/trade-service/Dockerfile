FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

# Install packages
COPY packages/kronos-factors /app/packages/kronos-factors
COPY packages/kronos-core /app/packages/kronos-core
COPY packages/kronos-data /app/packages/kronos-data
COPY packages/kronos-auth /app/packages/kronos-auth
RUN pip install --no-cache-dir \
    /app/packages/kronos-factors \
    /app/packages/kronos-core \
    /app/packages/kronos-data \
    /app/packages/kronos-auth

# Install service
COPY services/trade-service /app/service
RUN pip install --no-cache-dir /app/service

EXPOSE 8006
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
