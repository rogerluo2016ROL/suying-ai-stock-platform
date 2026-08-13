FROM suying-python-base:latest


COPY packages/kronos-auth /app/packages/kronos-auth
RUN pip install --no-cache-dir /app/packages/kronos-auth

# Install service
COPY services/strategy-service /app/service
RUN pip install --no-cache-dir /app/service

EXPOSE 8003
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
