import logging
import time
import asyncio
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from typing import Optional, Dict, List
import httpx
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import config
from . import metrics
from .models import (
    OCRResponse, BatchOCRRequest, BatchOCRResponse,
    HealthCheckResponse, ProgressResponse
)
from .pdf import PDFProcessor
from .ocr import OCRProcessor

logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    app = FastAPI(
        title="RPG Rules Engine - OCR Service",
        description=config.DESCRIPTION,
        version=config.VERSION
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Content-Type", "Accept", "Authorization", "Origin",
            "X-Requested-With", "X-Job-ID",
        ],
        expose_headers=["X-Job-ID"],
        max_age=3600,
    )

    # Add trusted host middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]
    )

    # Create thread pool
    thread_pool = ThreadPoolExecutor(max_workers=config.MAX_WORKERS)
    ocr_processor = OCRProcessor(thread_pool)

    @app.get("/", tags=["Status"])
    async def read_root():
        """Root endpoint for health checks"""
        return {"status": "healthy"}

    @app.get("/health", response_model=HealthCheckResponse, tags=["Status"])
    async def health_check():
        """Get detailed service health status"""
        return HealthCheckResponse(
            status="healthy",
            version=config.VERSION,
            queue_size=config.processing_queue.qsize(),
            active_workers=len([t for t in thread_pool._threads if t.is_alive()]),
            uptime=time.time() - config.start_time,
            last_processed=max([p.get('last_update') for p in config.job_progress.values()], default=None)
        )

    @app.get("/metrics", tags=["Monitoring"])
    async def get_metrics():
        """Get Prometheus metrics"""
        return Response(
            generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )

    @app.post(
        "/extract",
        response_model=OCRResponse,
        tags=["OCR"],
        summary="Extract text from a PDF file"
    )
    async def extract_text(
        file: UploadFile = File(..., description="PDF file to process"),
        dpi: Optional[int] = config.DEFAULT_DPI
    ):
        """Extract text from PDF files using Tesseract OCR with parallel page processing"""
        start_process_time = time.time()
        job_id = str(uuid.uuid4())
        
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        try:
            # Process PDF directly from memory
            content = await file.read()
            
            # Initialize progress tracking
            config.job_progress[job_id] = {
                'total_pages': 0,
                'processed_pages': 0,
                'status': 'processing',
                'start_time': start_process_time,
                'last_update': datetime.now()
            }
            
            # Process PDF
            pdf_processor = PDFProcessor(content, dpi=dpi)
            images = await pdf_processor.process()
            
            # Update progress tracking
            config.job_progress[job_id]['total_pages'] = len(images)
            
            # Define progress callback
            async def update_progress(processed_count: int):
                config.job_progress[job_id]['processed_pages'] += processed_count
                config.job_progress[job_id]['last_update'] = datetime.now()
                
                # Calculate estimated time remaining
                elapsed_time = time.time() - start_process_time
                if config.job_progress[job_id]['processed_pages'] > 0:
                    avg_time_per_page = elapsed_time / config.job_progress[job_id]['processed_pages']
                    remaining_pages = len(images) - config.job_progress[job_id]['processed_pages']
                    config.job_progress[job_id]['estimated_time_remaining'] = avg_time_per_page * remaining_pages
            
            # Process images with OCR
            results = await ocr_processor.process_document(images, on_progress=update_progress)
            
            # Calculate processing time
            processing_time = time.time() - start_process_time
            
            # Update progress
            config.job_progress[job_id]['status'] = 'completed'
            config.job_progress[job_id]['last_update'] = datetime.now()
            
            # Prepare response
            response = OCRResponse(
                text=ocr_processor.combine_text(results),
                metadata={
                    "num_pages": len(images),
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "parallel_processed": True,
                    "processing_time_seconds": processing_time,
                    "job_id": job_id,
                    "dpi": dpi,
                    "workers": config.MAX_WORKERS
                },
                confidence=ocr_processor.calculate_confidence(results),
                processing_time=processing_time
            )
            
            # Add job ID to response headers
            headers = {"X-Job-ID": job_id}
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
                headers=headers
            )
            
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/progress/{job_id}", response_model=ProgressResponse, tags=["Status"])
    async def get_progress(job_id: str):
        """Get progress information for a specific job"""
        if job_id not in config.job_progress:
            raise HTTPException(status_code=404, detail="Job not found")
        
        progress = config.job_progress[job_id]
        return ProgressResponse(
            job_id=job_id,
            total_pages=progress['total_pages'],
            processed_pages=progress['processed_pages'],
            status=progress['status'],
            progress_percentage=(progress['processed_pages'] / progress['total_pages'] * 100),
            estimated_time_remaining=progress.get('estimated_time_remaining')
        )

    @app.get("/progress-stream/{job_id}", tags=["Status"])
    async def progress_stream(job_id: str):
        """Stream progress updates for a job"""
        if job_id not in config.job_progress:
            raise HTTPException(status_code=404, detail="Job not found")
        
        async def event_generator():
            last_percent = -1
            try:
                while True:
                    if job_id in config.job_progress:
                        progress = config.job_progress[job_id]
                        total_pages = progress['total_pages']
                        processed_pages = progress['processed_pages']
                        percent = int((processed_pages / total_pages * 100) if total_pages > 0 else 0)
                        
                        if percent != last_percent or progress['status'] == 'completed':
                            last_percent = percent
                            data = {
                                "percent": percent,
                                "status": progress['status'],
                                "processed": processed_pages,
                                "total": total_pages,
                                "estimated_time": progress.get('estimated_time_remaining')
                            }
                            yield f"event: progress\ndata: {json.dumps(data)}\n\n"
                            
                            if progress['status'] == 'completed':
                                await asyncio.sleep(0.1)
                                break
                    
                    await asyncio.sleep(0.2)
                    
            except Exception as e:
                logger.error(f"Error in progress stream: {e}")
                error_data = {"error": str(e), "status": "error"}
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
            finally:
                if job_id in config.job_progress and progress['status'] == 'completed':
                    del config.job_progress[job_id]
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no'
            }
        )

    return app
