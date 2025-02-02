# Dunstan Rules Engine

A microservices-based system for extracting and processing rules from RPG sourcebooks.

## Features

- **Processing Agent**: Handles PDF chunk processing using various AI providers
  - FastAPI-based REST API for chunk processing and validation
  - Modular provider system for multiple AI integrations
  - Built-in result validation and error handling
  - Metrics collection for monitoring and optimization
  - Health check endpoint for system monitoring

- **OCR Engine Service**
  - PDF to text conversion with parallel page processing
  - Accurate confidence scoring (0-100%) for OCR quality assessment
  - High-quality image conversion with 400 DPI
  - Real-time progress tracking and status updates
  - Support for batch processing of multiple PDFs

- **OCR Web Interface**
  - Modern web interface for PDF uploads
  - Real-time progress monitoring
  - Detailed OCR results with confidence scores
  - Clean, responsive design

- **Validation Agents**
  - Human validation workflow
  - LLM-based validation
  - Rules-based validation

- **NLP Engine**
  - Text processing and analysis
  - Rules extraction capabilities

## Architecture

The system consists of several microservices:

- `services/ocr-engine`: Core OCR processing service
- `services/ocr-web`: Web interface for OCR operations
- `services/nlp-engine`: Natural language processing service
- `agents/validation`: Validation services (human, LLM, rules)

## Infrastructure

- Redis for caching and message queues
- Vector database for efficient text search
- Docker containerization for all services

## Development

See individual service READMEs for specific setup and development instructions.

## Documentation

- `docs/API.md`: API documentation
- `docs/ROLES.md`: Service roles and responsibilities
