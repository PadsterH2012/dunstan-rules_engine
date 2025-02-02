import multiprocessing
import os
import time
from asyncio import Queue

# Service Info
VERSION = "1.0.0"
DESCRIPTION = """
OCR Service for the RPG Rules Engine that extracts text from PDF documents.

Features:
- Single PDF processing with parallel page processing
- Batch processing of multiple PDFs from URLs
- Detailed metadata and confidence scores
"""

# Processing Configuration
MAX_WORKERS = min(32, (multiprocessing.cpu_count() or 4) + 4)  # CPU cores + 4 for I/O
MAX_BATCH_SIZE = 10
MAX_QUEUE_SIZE = 100
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1  # seconds
DEFAULT_DPI = 200  # Lower default DPI for faster processing

# OCR Configuration
TESSERACT_CONFIG = '--oem 1 --psm 3'  # Fast LSTM mode

# File System
TEMP_DIR = os.getenv('TMPDIR', '/tmp/ocr-work')

# Global State
processing_queue = Queue(maxsize=MAX_QUEUE_SIZE)
job_progress = {}
start_time = time.time()

# Logging Format
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'

# PDF Processing Options
PDF_OPTIONS = {
    'png': True,         # Output format
    'anti_alias': True,  # Enable anti-aliasing
    'cropbox': True,     # Use crop box
    'progress': True,    # Show conversion progress
    'verbose': True      # Detailed output
}
