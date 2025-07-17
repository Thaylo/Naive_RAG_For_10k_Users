FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/chunk_config /app/services/chunk_config

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.chunk_config.main:app", "--host", "0.0.0.0", "--port", "8002"]