# Production Dockerfile for FleedGuard Whitelist & SWISHBOT
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Install system dependencies (ffmpeg, libsodium, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libffi-dev \
    libnacl-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY . .

# Expose API/Dashboard port
EXPOSE 8000

# Start the Whitelist server on Railway's assigned PORT
CMD ["sh", "-c", "uvicorn fleed_whitelist.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
