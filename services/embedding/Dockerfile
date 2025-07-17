FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/embedding /app/services/embedding

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.embedding.main:app", "--host", "0.0.0.0", "--port", "8005"]