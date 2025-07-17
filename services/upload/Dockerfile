FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/upload /app/services/upload

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.upload.main:app", "--host", "0.0.0.0", "--port", "8003"]