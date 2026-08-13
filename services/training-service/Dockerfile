FROM suying-python-base:latest


COPY packages /app/packages
COPY configs /app/configs
COPY services/training-service/requirements.txt /tmp/training-requirements.txt
RUN pip install --no-cache-dir -r /tmp/training-requirements.txt

COPY services/training-service /app/service
WORKDIR /app/service

EXPOSE 8008
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
