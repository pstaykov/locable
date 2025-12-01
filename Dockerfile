FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/pstaykov/locable"
LABEL org.opencontainers.image.description="Locable - local AI-powered static site generator"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    OLLAMA_HOST=http://host.docker.internal:11434

WORKDIR /app

# System build deps required for chromadb/hnswlib wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy ONLY the Python package folder into the container
COPY locable /app/locable

EXPOSE 9200

# Start the FastAPI API server
CMD ["uvicorn", "locable.api:app", "--host", "0.0.0.0", "--port", "9200"]
