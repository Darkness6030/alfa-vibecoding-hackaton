FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Clean the Prometheus multiprocess dir before workers start (required for
# correct aggregation across workers).
CMD ["sh", "-c", "rm -rf /tmp/prometheus-multiproc && mkdir -p /tmp/prometheus-multiproc && PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc uvicorn app.main:app --host 0.0.0.0 --port 8000"]