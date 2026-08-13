FROM suying-python-base:latest

COPY packages/kronos-auth /app/packages/kronos-auth
RUN pip install --no-cache-dir /app/packages/kronos-auth

# Install system deps

# Copy and install packages actually used by screener-service.
COPY packages/kronos-factors /app/packages/kronos-factors
RUN pip install --no-cache-dir /app/packages/kronos-factors

# Copy service
COPY services/screener-service /app/service
RUN pip install --no-cache-dir /app/service

# Expose port
EXPOSE 8001

# Run
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
