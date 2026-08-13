FROM suying-python-base:latest


# Install packages
COPY packages/kronos-factors /app/packages/kronos-factors
COPY packages/kronos-data /app/packages/kronos-data
RUN pip install --no-cache-dir \
    /app/packages/kronos-factors \
    /app/packages/kronos-data

COPY packages/kronos-auth /app/packages/kronos-auth
RUN pip install --no-cache-dir /app/packages/kronos-auth

# Install service
COPY services/signal-service /app/service
RUN pip install --no-cache-dir /app/service

EXPOSE 8004
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
