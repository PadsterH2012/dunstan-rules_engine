import logging
import tempfile
import asyncio
from PIL import Image
import pytesseract
from typing import Dict, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
from . import config


logger = logging.getLogger(__name__)

class OCRProcessor:
    def __init__(self, thread_pool: ThreadPoolExecutor):
        self.thread_pool = thread_pool

    def process_page(self, image: Image.Image, page_id: str, page_num: int) -> Dict:
        """Process a single page with OCR"""
        try:
            # Process image directly in memory
            with tempfile.NamedTemporaryFile(suffix='.png', delete=True) as temp_img:
                image.save(temp_img, format='PNG')
                temp_img.seek(0)
                
                # Extract text using optimized Tesseract settings
                text = pytesseract.image_to_string(
                    temp_img.name, 
                    config=config.TESSERACT_CONFIG
                )
                
                # Get confidence score
                data = pytesseract.image_to_data(
                    temp_img.name, 
                    output_type=pytesseract.Output.DICT,
                    config=config.TESSERACT_CONFIG
                )
                
            # Calculate confidence only for valid scores
            valid_scores = [float(conf) for conf in data['conf'] if conf != '-1']
            page_confidence = sum(valid_scores) / len(valid_scores) if valid_scores else 0
            
            logger.info(f"Processed page {page_num + 1} (Confidence: {page_confidence:.1f}%)")
            
            return {
                'text': text,
                'confidence': page_confidence,
                'page': page_num + 1
            }
        except Exception as e:
            logger.error(f"Error processing page {page_num}: {str(e)}")
            return {
                'text': '',
                'confidence': 0,
                'page': page_num + 1,
                'error': str(e)
            }

    async def process_batch(
        self, 
        images: List[Image.Image], 
        batch_start: int, 
        batch_size: int,
        on_progress = None
    ) -> List[Dict]:
        """Process a batch of pages in parallel"""
        tasks = []
        loop = asyncio.get_event_loop()
        
        for i in range(batch_start, min(batch_start + batch_size, len(images))):
            task = loop.run_in_executor(
                self.thread_pool,
                self.process_page,
                images[i],
                f"page_{i}",
                i
            )
            tasks.append(task)
        
        batch_results = await asyncio.gather(*tasks)
        
        if on_progress:
            await on_progress(len(batch_results))
        
        return batch_results

    async def process_document(
        self, 
        images: List[Image.Image],
        on_progress = None
    ) -> List[Dict]:
        """Process all pages in a document using batched execution"""
        results = []
        batch_size = config.MAX_WORKERS * 2  # Process multiple batches for better throughput
        
        for i in range(0, len(images), batch_size):
            batch_results = await self.process_batch(
                images, 
                batch_start=i, 
                batch_size=batch_size,
                on_progress=on_progress
            )
            results.extend(batch_results)
        
        # Sort results by page number
        results.sort(key=lambda x: x['page'])
        return results

    def calculate_confidence(self, results: List[Dict]) -> float:
        """Calculate average confidence across all pages"""
        if not results:
            return 0.0
        total_confidence = sum(r['confidence'] for r in results)
        return total_confidence / len(results)

    def combine_text(self, results: List[Dict]) -> str:
        """Combine text from all pages"""
        return "\n".join(r['text'] for r in results)
