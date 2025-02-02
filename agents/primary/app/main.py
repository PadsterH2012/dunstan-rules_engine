from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import httpx
import hashlib
import logging
from .utils.cache import get_from_cache, set_to_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="RPG Rules Engine - Primary Agent")

# Configuration
OCR_SERVICE_URL = "http://ocr-engine:8000"
PDF_CACHE_TTL = 604800  # 7 days in seconds

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    source: str
    confidence: float

class OCRResponse(BaseModel):
    text: str
    metadata: Dict[str, Any]
    confidence: float

class PDFProcessingResponse(BaseModel):
    text: str
    metadata: Dict[str, Any]
    confidence: float
    cached: bool

def generate_file_hash(content: bytes) -> str:
    """Generate a unique hash for the file content."""
    return hashlib.sha256(content).hexdigest()

@app.get("/", response_model=str)
async def read_root():
    return "Welcome to the RPG Rules Engine - Primary Agent"

@app.post("/process-pdf", response_model=PDFProcessingResponse)
async def process_pdf(file: UploadFile = File(...)):
    """
    Process a PDF file through the OCR service with caching support.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        content = await file.read()
        file_hash = generate_file_hash(content)
        cache_key = f"pdf:ocr:{file_hash}"

        # Check cache first
        cached_result = get_from_cache(cache_key)
        if cached_result:
            logger.info(f"Cache hit for PDF: {file.filename}")
            cached_result['cached'] = True
            return PDFProcessingResponse(**cached_result)

        logger.info(f"Processing new PDF: {file.filename}")
        
        # Forward to OCR service
        async with httpx.AsyncClient() as client:
            files = {'file': (file.filename, content, 'application/pdf')}
            response = await client.post(f"{OCR_SERVICE_URL}/extract", files=files)
            
            if response.status_code != 200:
                logger.error(f"OCR service error: {response.text}")
                raise HTTPException(status_code=502, detail="OCR service error")

            result = response.json()
            result['cached'] = False
            
            # Cache the result
            set_to_cache(cache_key, result, PDF_CACHE_TTL)
            logger.info(f"Cached OCR results for: {file.filename}")
            
            return PDFProcessingResponse(**result)

    except httpx.RequestError as e:
        logger.error(f"Error communicating with OCR service: {str(e)}")
        raise HTTPException(status_code=503, detail="OCR service unavailable")
    except Exception as e:
        logger.error(f"Unexpected error processing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/query", response_model=QueryResponse)
async def query_rules(request: QueryRequest):
    # Normalize the query to generate a cache key.
    key = f"traveller:query:{request.query.lower().replace(' ', '_')}"
    cached_result = get_from_cache(key)
    if cached_result:
        logger.info(f"Cache hit for query: {request.query}")
        return cached_result

    # Dummy processing: Replace with calls to OCR, NLP, and validation services.
    result = {
        "answer": "3d6",
        "source": "Traveller Core Rulebook p. 89",
        "confidence": 0.95
    }

    # Cache the result
    set_to_cache(key, result)
    logger.info(f"Cached new query result: {request.query}")
    return result
