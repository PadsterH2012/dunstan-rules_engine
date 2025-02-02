import multiprocessing as mp
from typing import Dict, Any
import pytesseract
from PIL import Image
import os
import tempfile
import logging

logger = logging.getLogger(__name__)

def process_page_mp(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single page using multiprocessing.
    This function runs in a separate process for CPU-bound OCR tasks.
    """
    image = args['image']
    temp_pdf_path = args['temp_pdf_path']
    page_num = args['page_num']
    
    temp_image_path = f"{temp_pdf_path}_page_{page_num}.png"
    try:
        # Save image temporarily
        image.save(temp_image_path)
        
        # Extract text using Tesseract
        text = pytesseract.image_to_string(temp_image_path)
        
        # Get confidence score
        data = pytesseract.image_to_data(temp_image_path, output_type=pytesseract.Output.DICT)
        page_confidence = sum(float(conf) for conf in data['conf'] if conf != '-1') / len(data['conf'])
        
        logger.info(f"Processed page {page_num + 1} with confidence {page_confidence}")
        
        return {
            'text': text,
            'confidence': page_confidence,
            'page': page_num + 1
        }
    finally:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)

class OCRWorkerPool:
    """
    Manages a pool of worker processes for OCR tasks.
    """
    def __init__(self, max_workers: int = None):
        if max_workers is None:
            max_workers = mp.cpu_count()
        self.max_workers = max_workers
        self.pool = mp.Pool(processes=max_workers)
        logger.info(f"Initialized OCR worker pool with {max_workers} workers")
    
    def process_pages(self, images: list, temp_pdf_path: str) -> list:
        """
        Process multiple pages in parallel using the worker pool.
        """
        tasks = [
            {
                'image': image,
                'temp_pdf_path': temp_pdf_path,
                'page_num': i
            }
            for i, image in enumerate(images)
        ]
        
        logger.info(f"Processing {len(tasks)} pages using {self.max_workers} workers")
        results = self.pool.map(process_page_mp, tasks)
        
        # Sort results by page number
        results.sort(key=lambda x: x['page'])
        return results
    
    def shutdown(self):
        """
        Clean up worker pool resources.
        """
        self.pool.close()
        self.pool.join()
        logger.info("OCR worker pool shut down")
