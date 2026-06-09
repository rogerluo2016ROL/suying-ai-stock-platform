FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

# Copy and install packages
COPY packages/kronos-factors /app/packages/kronos-factors
COPY packages/kronos-core /app/packages/kronos-core
COPY packages/kronos-data /app/packages/kronos-data
RUN pip install --no-cache-dir \
    /app/packages/kronos-factors \
    /app/packages/kronos-core \
    /app/packages/kronos-data

# Copy service
COPY services/screener-service /app/service
RUN pip install --no-cache-dir /app/service

# Expose port
EXPOSE 8001

# Run
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
