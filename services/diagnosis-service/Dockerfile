FROM suying-python-base:latest

COPY packages/kronos-auth /app/packages/kronos-auth
RUN pip install --no-cache-dir /app/packages/kronos-auth

# Install packages
COPY packages/kronos-factors /app/packages/kronos-factors
RUN pip install --no-cache-dir \
    /app/packages/kronos-factors

# Install service
COPY services/diagnosis-service /app/service
RUN pip install --no-cache-dir /app/service

EXPOSE 8009
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
