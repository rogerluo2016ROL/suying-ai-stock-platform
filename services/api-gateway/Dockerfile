FROM suying-python-base:latest

# 网关侧 JWT 验签依赖共享认证包
COPY packages/kronos-auth /app/packages/kronos-auth
RUN pip install --no-cache-dir /app/packages/kronos-auth

# API Gateway is self-contained (no package deps)
COPY services/api-gateway /app/service
RUN pip install --no-cache-dir fastapi uvicorn[standard]

EXPOSE 8080
WORKDIR /app/service
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
