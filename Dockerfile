FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir "google-cloud-bigquery>=3.25"
COPY outputs/ ./outputs/
COPY dashboard_server.py ./

ENV PORT=8080
EXPOSE 8080

CMD ["python", "dashboard_server.py"]
