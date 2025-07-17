FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/rag_query /app/services/rag_query

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.rag_query.main:app", "--host", "0.0.0.0", "--port", "8007"]