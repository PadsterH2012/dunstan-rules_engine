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
DEFAULT_DPI = 400  # Higher DPI for better OCR accuracy

# OCR Configuration
TESSERACT_CONFIG = '--oem 1 --psm 3'  # Fast LSTM mode

# File System
TEMP_DIR = os.getenv('TMPDIR', '/tmp/ocr-work')

# Ensure temp directory exists with proper permissions
try:
    # First try to use existing directory
    if os.path.exists(TEMP_DIR):
        if os.access(TEMP_DIR, os.W_OK):
            print(f"Using existing temp directory: {TEMP_DIR}")
        else:
            # Try user's home directory as fallback
            TEMP_DIR = os.path.join(os.path.expanduser('~'), '.ocr-work')
            os.makedirs(TEMP_DIR, mode=0o700, exist_ok=True)
            print(f"Using fallback temp directory: {TEMP_DIR}")
    else:
        # Try to create the default directory
        os.makedirs(TEMP_DIR, mode=0o777, exist_ok=True)
        os.chmod(TEMP_DIR, 0o777)
        print(f"Created temp directory: {TEMP_DIR}")
except Exception as e:
    # Use /tmp as last resort
    TEMP_DIR = '/tmp'
    print(f"Warning: Using /tmp as fallback directory: {e}")

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
