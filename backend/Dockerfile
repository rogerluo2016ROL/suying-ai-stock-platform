FROM suying-python-base:latest

# Copy backend
COPY backend /app/backend

# Install backend dependencies (单一来源: backend/requirements.txt)
RUN pip install --no-cache-dir -r backend/requirements.txt

EXPOSE 9001
# AC-8: alembic upgrade head runs inside main.py lifespan (covers docker compose +
# manual `uvicorn` start uniformly), so the Dockerfile just boots uvicorn in the
# backend/ workdir where `app.main` is importable.
WORKDIR /app/backend
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9001"]
