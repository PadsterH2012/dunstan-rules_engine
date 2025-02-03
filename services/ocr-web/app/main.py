import os
import asyncio
import logging
import shutil
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
from contextlib import contextmanager


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
    expose_headers=["Content-Type", "X-Job-ID"],
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
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB default
MIN_DISK_SPACE = int(os.getenv("MIN_DISK_SPACE", str(500 * 1024 * 1024)))  # 500MB default
TEMP_DIR = os.getenv("OCR_TEMP_DIR", "/app/tmp")  # Use mounted volume for temp files

@contextmanager
def temporary_directory():
    """Create a temporary directory that's automatically cleaned up"""
    temp_dir = os.path.join(TEMP_DIR, f'ocr_{uuid.uuid4().hex}')
    os.makedirs(temp_dir, exist_ok=True)
    try:
        yield temp_dir
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Error cleaning up temporary directory {temp_dir}: {e}")

def check_disk_space(path: str = TEMP_DIR) -> bool:
    """Check if there's enough disk space available"""
    stats = shutil.disk_usage(path)
    return stats.free >= MIN_DISK_SPACE

def get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    return os.path.getsize(file_path)

class PDFChunker:
    def __init__(self, file_path: str, chunk_size: int, overlap: int, chunk_dir: str):
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunk_dir = chunk_dir
        self.total_pages = 0
        self.chunks: List[Dict] = []

    async def process(self) -> List[Dict]:
        """Split PDF into overlapping chunks"""
        try:
            with open(self.file_path, 'rb') as file:
                pdf = PyPDF2.PdfReader(file)
                self.total_pages = len(pdf.pages)
                
                # For small PDFs (less than chunk_size), create a single chunk
                if self.total_pages <= self.chunk_size:
                    chunk_id = str(uuid.uuid4())
                    chunk_dir = os.path.join(self.chunk_dir, chunk_id)
                    os.makedirs(chunk_dir, exist_ok=True)
                    
                    chunk_path = os.path.join(chunk_dir, 'chunk.pdf')
                    writer = PyPDF2.PdfWriter()
                    
                    for page_num in range(self.total_pages):
                        writer.add_page(pdf.pages[page_num])
                    
                    with open(chunk_path, 'wb') as chunk_file:
                        writer.write(chunk_file)
                    
                    self.chunks.append({
                        'id': chunk_id,
                        'path': chunk_path,
                        'start_page': 1,
                        'end_page': self.total_pages,
                        'total_pages': self.total_pages
                    })
                    return self.chunks
                
                # For larger PDFs, create overlapping chunks
                start_page = 0
                while start_page < self.total_pages:
                    # Check disk space before creating chunk
                    if not check_disk_space():
                        raise Exception("Insufficient disk space for creating PDF chunk")
                    
                    end_page = min(start_page + self.chunk_size, self.total_pages)
                    
                    # Skip creating a new chunk if it would be too small
                    if end_page - start_page < 2 and len(self.chunks) > 0:
                        break
                    
                    # Create chunk directory
                    chunk_id = str(uuid.uuid4())
                    chunk_dir = os.path.join(self.chunk_dir, chunk_id)
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
                        
                    # Verify chunk size
                    chunk_size = get_file_size(chunk_path)
                    if chunk_size > MAX_FILE_SIZE:
                        os.remove(chunk_path)
                        raise Exception(f"Chunk size {chunk_size/1024/1024:.1f}MB exceeds maximum allowed size")
                    
                    self.chunks.append({
                        'id': chunk_id,
                        'path': chunk_path,
                        'start_page': start_page + 1,
                        'end_page': end_page,
                        'total_pages': end_page - start_page
                    })
                    
                    # Move start_page for next chunk, including overlap
                    # Ensure we make meaningful progress
                    progress = max(1, self.chunk_size - self.overlap)
                    start_page += progress

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
                    if result['status'] == 'success':
                        self.jobs[job_id]['results'].append({
                            'result': result['result'],
                            'page_range': result['page_range']
                        })
                        self.jobs[job_id]['completed_chunks'] += 1
                        
                        # Check if all chunks are processed
                        if self.jobs[job_id]['completed_chunks'] == self.jobs[job_id]['total_chunks']:
                            await self.finalize_job(job_id)
                    else:
                        raise Exception(result['message'])
        
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
            
            # Clean up chunk files if they still exist
            for chunk in job['chunks']:
                try:
                    if os.path.exists(chunk['path']):
                        os.remove(chunk['path'])
                        chunk_dir = os.path.dirname(chunk['path'])
                        if os.path.exists(chunk_dir) and not os.listdir(chunk_dir):
                            os.rmdir(chunk_dir)
                except Exception as e:
                    logger.debug(f"Chunk {chunk['id']} already cleaned up or error: {str(e)}")
                    
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
    
    if not check_disk_space():
        raise HTTPException(
            status_code=507,
            detail="Insufficient disk space available"
        )
    
    try:
        # Create temporary file with automatic cleanup
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_path = temp_file.name
            content = await file.read()
            
            # Check file size
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {MAX_FILE_SIZE/1024/1024:.1f}MB"
                )
            
            temp_file.write(content)
        
        # Create temporary directory for chunks
        with temporary_directory() as chunk_dir:
            # Split into chunks
            chunker = PDFChunker(temp_path, CHUNK_SIZE, CHUNK_OVERLAP, chunk_dir)
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
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.error(f"Error removing temporary file {temp_path}: {e}")
        
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
