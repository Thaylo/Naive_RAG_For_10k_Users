FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/chunking /app/services/chunking

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.chunking.main:app", "--host", "0.0.0.0", "--port", "8004"]