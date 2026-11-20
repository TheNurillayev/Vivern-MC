# Dockerfile for Vivern MC Production Deployment
FROM python:3.12-slim

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY backend /app/backend
COPY web /app/web
COPY run_server.py /app/run_server.py
COPY .env.example /app/.env.example
COPY storage/library /app/storage/library
COPY storage/library /app/default_assets/library

# Create storage directories
RUN mkdir -p /app/storage/library /app/storage/uploads /app/storage/outputs /app/default_assets/library

# Expose port
EXPOSE 8000

# Run server with auto-restart
CMD ["python", "run_server.py"]
