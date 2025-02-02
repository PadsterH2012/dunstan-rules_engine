from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx
import asyncio
from typing import Optional
import json
import os

app = FastAPI(
    title="OCR Web Interface",
    description="Web interface for the OCR Engine service",
    version="1.0.0"
)

# Add CORS middleware with specific settings for file uploads
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Accept",
        "Authorization",
        "Origin",
        "X-Requested-With",
        "X-Job-ID",
    ],
    expose_headers=["X-Job-ID"],  # Allow client to read the job ID header
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Add trusted host middleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Mount static files directory
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# OCR service configuration
OCR_SERVICE_URL = os.getenv('OCR_ENGINE_URL', 'http://localhost:8001')

@app.get("/health")
async def root_health():
    """Root health check endpoint"""
    return {"status": "healthy"}

@app.get("/", response_class=HTMLResponse, include_in_schema=True)
async def read_root():
    """Serve the upload interface"""
    return FileResponse('app/static/index.html')

@app.post("/api/extract")
async def proxy_extract(file: UploadFile = File(...)):
    """Proxy file upload to OCR service"""
    try:
        print(f"Received file upload: {file.filename}, content_type: {file.content_type}")
        
        # Read file content
        content = await file.read()
        print(f"File size: {len(content)} bytes")
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=300.0)) as client:  # 5 minute timeout
            # Create a new UploadFile with the content
            files = {'file': (file.filename, content, file.content_type)}
            print(f"Sending request to OCR service: {OCR_SERVICE_URL}/extract")
            
            response = await client.post(f"{OCR_SERVICE_URL}/extract", files=files)
            print(f"OCR service response status: {response.status_code}")
            
            # Get the response content
            content = await response.aread()
            
            # Create a new response with the same headers and content
            return Response(
                content=content,
                status_code=response.status_code,
                headers=response.headers,
                media_type=response.headers.get('content-type', 'application/json')
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request timed out while processing the PDF. The file might be too large or complex."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PDF: {str(e)}"
        )

@app.get("/api/progress-stream/{job_id}")
async def proxy_progress_stream(job_id: str):
    """Proxy progress stream from OCR service"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=None)) as client:  # No timeout for SSE
            response = await client.get(
                f"{OCR_SERVICE_URL}/progress-stream/{job_id}",
                headers={"Accept": "text/event-stream"}
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Error from OCR service: {response.text}"
                )
            return StreamingResponse(
                response.aiter_bytes(),
                media_type="text/event-stream",
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no'  # Disable proxy buffering
                }
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Connection to OCR service timed out"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to OCR service: {str(e)}"
        )

@app.get("/api/health")
async def health_check():
    """Check health of web interface and OCR service"""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=5.0)) as client:  # 5 second timeout
            ocr_health = await client.get(f"{OCR_SERVICE_URL}/health")
            ocr_status = "healthy" if ocr_health.status_code == 200 else "unhealthy"
            ocr_details = await ocr_health.json() if ocr_health.status_code == 200 else None
    except httpx.TimeoutException:
        ocr_status = "timeout"
        ocr_details = None
    except Exception as e:
        ocr_status = "unreachable"
        ocr_details = str(e)
    
    return {
        "status": "healthy",
        "ocr_service": {
            "status": ocr_status,
            "details": ocr_details
        }
    }
