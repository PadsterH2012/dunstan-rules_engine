import os
import asyncio
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import aiohttp
import uuid
import json
from PIL import Image
import PyPDF2
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OCR Web Interface")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add cache control middleware
@app.middleware("http")
async def add_cache_control_header(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

# Serve static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
async def root():
    return FileResponse("app/static/index.html")

# Configuration
CHUNK_SIZE = int(os.getenv("PDF_CHUNK_SIZE", "20"))
CHUNK_OVERLAP = int(os.getenv("PDF_CHUNK_OVERLAP", "2"))
PROCESSING_AGENT_URL = os.getenv("PROCESSING_AGENT_URL", "http://processing-agent:8000")
TEMP_DIR = os.getenv("PDF_TEMP_DIR", "/tmp/pdf-chunks")

# Ensure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)

class PDFChunker:
    def __init__(self, file_path: str, chunk_size: int, overlap: int):
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.total_pages = 0
        self.chunks: List[Dict] = []

    async def process(self) -> List[Dict]:
        """Split PDF into overlapping chunks"""
        try:
            with open(self.file_path, 'rb') as file:
                pdf = PyPDF2.PdfReader(file)
                self.total_pages = len(pdf.pages)
                
                # Calculate chunks with overlap
                start_page = 0
                while start_page < self.total_pages:
                    end_page = min(start_page + self.chunk_size, self.total_pages)
                    
                    # Create chunk directory
                    chunk_id = str(uuid.uuid4())
                    chunk_dir = os.path.join(TEMP_DIR, chunk_id)
                    os.makedirs(chunk_dir, exist_ok=True)
                    
                    # Create new PDF for chunk
                    chunk_path = os.path.join(chunk_dir, 'chunk.pdf')
                    writer = PyPDF2.PdfWriter()
                    
                    # Add pages to chunk
                    for page_num in range(start_page, end_page):
                        writer.add_page(pdf.pages[page_num])
                    
                    # Save chunk
                    with open(chunk_path, 'wb') as chunk_file:
                        writer.write(chunk_file)
                    
                    self.chunks.append({
                        'id': chunk_id,
                        'path': chunk_path,
                        'start_page': start_page + 1,
                        'end_page': end_page,
                        'total_pages': end_page - start_page
                    })
                    
                    # Move start_page for next chunk, including overlap
                    start_page = end_page - self.overlap

                logger.info(f"Split PDF into {len(self.chunks)} chunks")
                return self.chunks
                
        except Exception as e:
            logger.error(f"Error splitting PDF: {str(e)}")
            raise

class ProcessingManager:
    def __init__(self):
        self.jobs: Dict[str, Dict] = {}

    async def create_job(self, file_name: str, chunks: List[Dict]) -> str:
        """Create new processing job"""
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            'id': job_id,
            'file_name': file_name,
            'status': 'processing',
            'chunks': chunks,
            'results': [],
            'completed_chunks': 0,
            'total_chunks': len(chunks)
        }
        return job_id

    async def process_chunk(self, job_id: str, chunk: Dict):
        """Send chunk to processing agent"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PROCESSING_AGENT_URL}/process",
                    json={
                        'job_id': job_id,
                        'chunk_id': chunk['id'],
                        'file_path': chunk['path'],
                        'page_range': {
                            'start': chunk['start_page'],
                            'end': chunk['end_page']
                        }
                    }
                ) as response:
                    if response.status != 200:
                        raise Exception(f"Processing failed: {await response.text()}")
                    
                    result = await response.json()
                    self.jobs[job_id]['results'].append(result)
                    self.jobs[job_id]['completed_chunks'] += 1
                    
                    # Check if all chunks are processed
                    if self.jobs[job_id]['completed_chunks'] == self.jobs[job_id]['total_chunks']:
                        await self.finalize_job(job_id)
        
        except Exception as e:
            logger.error(f"Error processing chunk: {str(e)}")
            self.jobs[job_id]['status'] = 'error'
            self.jobs[job_id]['error'] = str(e)

    async def finalize_job(self, job_id: str):
        """Combine results and clean up"""
        try:
            job = self.jobs[job_id]
            
            # Sort results by page number
            job['results'].sort(key=lambda x: x['page_range']['start'])
            
            # Update status
            job['status'] = 'completed'
            
            # Clean up chunk files
            for chunk in job['chunks']:
                try:
                    os.remove(chunk['path'])
                    os.rmdir(os.path.dirname(chunk['path']))
                except Exception as e:
                    logger.warning(f"Error cleaning up chunk {chunk['id']}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error finalizing job: {str(e)}")
            self.jobs[job_id]['status'] = 'error'
            self.jobs[job_id]['error'] = str(e)

# Initialize processing manager
processing_manager = ProcessingManager()

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """Handle file upload and start processing"""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    try:
        # Save uploaded file
        temp_path = os.path.join(TEMP_DIR, f"upload_{uuid.uuid4()}.pdf")
        with open(temp_path, 'wb') as temp_file:
            content = await file.read()
            temp_file.write(content)
        
        # Split into chunks
        chunker = PDFChunker(temp_path, CHUNK_SIZE, CHUNK_OVERLAP)
        chunks = await chunker.process()
        
        # Create processing job
        job_id = await processing_manager.create_job(file.filename, chunks)
        
        # Start processing chunks
        for chunk in chunks:
            background_tasks.add_task(
                processing_manager.process_chunk,
                job_id,
                chunk
            )
        
        # Clean up uploaded file
        os.remove(temp_path)
        
        return JSONResponse({
            'job_id': job_id,
            'file_name': file.filename,
            'total_pages': chunker.total_pages,
            'total_chunks': len(chunks)
        })
        
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get job status"""
    if job_id not in processing_manager.jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = processing_manager.jobs[job_id]
    return {
        'id': job['id'],
        'status': job['status'],
        'file_name': job['file_name'],
        'progress': {
            'completed_chunks': job['completed_chunks'],
            'total_chunks': job['total_chunks'],
            'percentage': (job['completed_chunks'] / job['total_chunks']) * 100
        },
        'error': job.get('error')
    }

@app.get("/result/{job_id}")
async def get_result(job_id: str):
    """Get job results"""
    if job_id not in processing_manager.jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = processing_manager.jobs[job_id]
    if job['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Job not completed")
    
    return {
        'id': job['id'],
        'file_name': job['file_name'],
        'results': job['results']
    }
