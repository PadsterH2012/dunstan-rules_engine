FROM python:3.9-slim

WORKDIR /app

# Set PYTHONPATH to include the app directory
ENV PYTHONPATH=/app

# Install system dependencies including Tesseract, Poppler, and curl for healthchecks
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create and set permissions for temp directory
RUN mkdir -p /tmp/ocr-work && \
    chmod 777 /tmp/ocr-work && \
    chown -R nobody:nogroup /tmp/ocr-work

# Set temp directory with write permissions
ENV TMPDIR=/tmp/ocr-work

# Install Python dependencies first as root
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app/ ./app/

# Set permissions for app directory
RUN chown -R nobody:nogroup /app

# Switch to non-root user
USER nobody

EXPOSE 8000

# Run the FastAPI app using Uvicorn with dynamic port
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers
