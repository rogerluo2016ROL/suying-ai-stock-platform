FROM python:3.11-slim

WORKDIR /app

# API Gateway is self-contained (no package deps)
COPY services/api-gateway /app/service
RUN pip install --no-cache-dir fastapi uvicorn[standard]

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
