FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

COPY packages/kronos-factors /app/packages/kronos-factors
RUN pip install --no-cache-dir /app/packages/kronos-factors

COPY services/backtest-service /app/service
RUN pip install --no-cache-dir /app/service

EXPOSE 8007
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
