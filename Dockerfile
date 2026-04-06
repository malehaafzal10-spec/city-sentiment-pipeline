FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p artifacts/raw artifacts/processed artifacts/features \
    artifacts/model_outputs artifacts/weekly artifacts/monitoring \
    artifacts/dashboard artifacts/logs docs
ENV PIPELINE_DB_PATH=artifacts/pipeline.db
ENV PIPELINE_ARTIFACTS_DIR=artifacts
CMD ["python", "run_pipeline.py"]
