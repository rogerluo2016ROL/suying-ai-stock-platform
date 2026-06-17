FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

# Install packages
COPY packages/kronos-factors /app/packages/kronos-factors
COPY packages/kronos-core /app/packages/kronos-core
COPY packages/kronos-data /app/packages/kronos-data
RUN pip install --no-cache-dir \
    /app/packages/kronos-factors \
    /app/packages/kronos-core \
    /app/packages/kronos-data

# Install service
COPY services/diagnosis-service /app/service
RUN pip install --no-cache-dir /app/service

EXPOSE 8009
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
