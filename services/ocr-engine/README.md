# OCR Service

A high-performance OCR service for the RPG Rules Engine that extracts text from PDF documents using Tesseract OCR.

## Features

- Single PDF processing with parallel page processing
- Batch processing of multiple PDFs from URLs
- Detailed metadata and confidence scoring
- Comprehensive error handling
- API documentation with Swagger/OpenAPI
- Test suite with unit and integration tests

## Requirements

- Python 3.9+
- Tesseract OCR
- Poppler (for PDF processing)
- Redis (for caching through primary agent)

## Installation

1. Install system dependencies:

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils

# macOS
brew install tesseract poppler
```

2. Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Running the Service

Start the service using uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or using Docker:

```bash
docker compose up ocr-engine
```

## API Documentation

The API documentation is available at:
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

### Endpoints

#### 1. Extract Text from PDF (`POST /extract`)

Process a single PDF file and extract text using OCR.

```bash
curl -X POST "http://localhost:8001/extract" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "text": "Extracted text content...",
  "metadata": {
    "num_pages": 5,
    "filename": "document.pdf",
    "content_type": "application/pdf",
    "parallel_processed": true
  },
  "confidence": 0.95
}
```

#### 2. Batch Process PDFs (`POST /batch-extract`)

Process multiple PDFs from provided URLs.

```bash
curl -X POST "http://localhost:8001/batch-extract" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://example.com/doc1.pdf",
      "https://example.com/doc2.pdf"
    ]
  }'
```

Response:
```json
{
  "results": [
    {
      "text": "Extracted text from first PDF...",
      "metadata": {
        "num_pages": 3,
        "source_url": "https://example.com/doc1.pdf",
        "parallel_processed": true
      },
      "confidence": 0.92
    }
  ],
  "failed_urls": [
    "https://example.com/doc2.pdf"
  ]
}
```

## Testing

Run the test suite:

```bash
pytest
```

Run with coverage report:

```bash
pytest --cov=app --cov-report=term-missing
```

## Performance Considerations

- The service uses parallel processing for both individual PDFs (page-level) and batch requests (document-level)
- Default thread pool size is 4 workers, configurable based on system resources
- For large PDFs, memory usage should be monitored
- Caching is handled by the primary agent to prevent reprocessing of the same documents

## Error Handling

- Invalid file types are rejected with appropriate error messages
- Network errors during batch processing are handled gracefully
- Failed URLs in batch requests are tracked and reported
- Temporary files are properly cleaned up

## Integration with Primary Agent

The OCR service is designed to work with the primary agent, which handles:
- Caching of OCR results
- Request routing
- Rate limiting
- Authentication (if required)

## Contributing

1. Run tests before submitting changes
2. Update documentation for any new features
3. Follow the existing code style
4. Add appropriate error handling
