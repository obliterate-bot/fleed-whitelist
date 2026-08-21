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
    nodejs \
    npm \
    lua5.1 \
    liblua5.1-0-dev \
    luajit \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY . .
RUN chmod +x /app/start.sh

# Expose API/Dashboard port
EXPOSE 8000

# Start both Whitelist API and Discord Bot
CMD ["/bin/bash", "/app/start.sh"]
