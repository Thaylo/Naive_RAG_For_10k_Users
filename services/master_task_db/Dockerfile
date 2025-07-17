FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY services/master_task_db /app/services/master_task_db

ENV PYTHONPATH=/app

CMD ["uvicorn", "services.master_task_db.main:app", "--host", "0.0.0.0", "--port", "8001"]