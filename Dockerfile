# 1. Lightweight Python Base Image
FROM python:3.11-slim

# 2. Optimize Python Runtime Settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# 3. System Dependencies (libgomp1 is required for LightGBM C++ OpenMP execution)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 4. Dependency Installation Layer (Leverages Docker Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 5. Copy Application Source Code & Configuration
COPY src/ ./src/
COPY config/ ./config/

# Create models and tmp directory for runtime artifact storage
RUN mkdir -p models /tmp

# 6. Create Non-Privileged User for Enterprise Security
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app /tmp

USER appuser

EXPOSE 8080

# 7. Start Low-Latency Uvicorn Server
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT}"]