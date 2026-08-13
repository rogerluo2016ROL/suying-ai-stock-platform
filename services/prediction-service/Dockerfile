FROM suying-python-base:latest

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

COPY packages/kronos-factors /app/packages/kronos-factors
COPY packages/kronos-core /app/packages/kronos-core
RUN pip install --no-cache-dir /app/packages/kronos-factors /app/packages/kronos-core

COPY packages/kronos-auth /app/packages/kronos-auth
RUN pip install --no-cache-dir /app/packages/kronos-auth

COPY services/prediction-service /app/service
RUN pip install --no-cache-dir /app/service

EXPOSE 8002
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
