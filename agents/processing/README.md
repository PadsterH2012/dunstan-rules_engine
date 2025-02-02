# Processing Agent

## Overview
The Processing Agent is designed to handle PDF chunk processing using various AI providers. It provides an API for processing chunks, validating results, and collecting metrics.

## Running the Service
To run the Processing Agent, use Docker Compose:

```bash
docker-compose up
```

This will start the Processing Agent along with Redis for job caching.

## API Endpoints

### POST /process
- **Description**: Processes a PDF chunk.
- **Request Body**: 
  ```json
  {
    "chunk": "string"
  }
  ```
- **Response**:
  ```json
  {
    "status": "success",
    "result": "Processed: <chunk>"
  }
  ```

### GET /health
- **Description**: Health check endpoint.
- **Response**:
  ```json
  {
    "status": "healthy"
  }
  ```

### GET /metrics
- **Description**: Collects and returns processing metrics.
- **Response**:
  ```json
  {
    "status": "metrics collected"
  }
  ```

## Dependencies
- FastAPI
- Redis
