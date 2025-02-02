FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./app ./app

# Create temp directory for PDF chunks
RUN mkdir -p /tmp/pdf-chunks && \
    chmod 777 /tmp/pdf-chunks

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PDF_TEMP_DIR=/tmp/pdf-chunks

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
