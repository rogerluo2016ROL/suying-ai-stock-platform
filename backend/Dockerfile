FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

# Copy backend
COPY backend /app/backend

# Install backend dependencies
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] \
    sqlalchemy[asyncio] asyncpg psycopg2-binary \
    alembic argon2-cffi pyjwt pydantic

EXPOSE 9001
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9001"]
