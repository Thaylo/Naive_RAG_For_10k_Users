FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/vectorial_db /app/services/vectorial_db

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.vectorial_db.main:app", "--host", "0.0.0.0", "--port", "8006"]