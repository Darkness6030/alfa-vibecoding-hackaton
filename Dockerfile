FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home appuser
COPY app ./app
COPY config ./config
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "rm -rf /tmp/prometheus-multiproc && mkdir -p /tmp/prometheus-multiproc && PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${ALFAGEN_WORKERS:-1} --no-access-log --loop uvloop --http httptools"]
