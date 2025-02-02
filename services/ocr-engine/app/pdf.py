import os
import uuid
import subprocess
import logging
import tempfile
import shutil
import asyncio
import multiprocessing
from PIL import Image
from typing import List, Dict, Tuple
import re
from . import config


logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self, content: bytes, dpi: int = config.DEFAULT_DPI):
        self.content = content
        self.dpi = dpi
        self.job_dir = os.path.join(config.TEMP_DIR, str(uuid.uuid4()))
        self.pdf_path = os.path.join(self.job_dir, 'input.pdf')
        self.metadata = {}
        self.page_count = 0

    async def setup(self):
        """Initialize working directory and save PDF"""
        os.makedirs(self.job_dir, exist_ok=True)
        with open(self.pdf_path, 'wb') as f:
            f.write(self.content)

    async def validate_pdf(self) -> Tuple[int, Dict]:
        """Validate PDF and extract metadata"""
        try:
            logger.info("Getting PDF information...")
            pdfinfo_output = subprocess.check_output(
                ['pdfinfo', '-box', '-meta', self.pdf_path],
                stderr=subprocess.PIPE
            ).decode()
            
            logger.info(f"Raw pdfinfo output:\n{pdfinfo_output}")
            
            # Extract metadata
            for field in ['Title', 'Author', 'Creator', 'Producer', 'File size', 'Pages']:
                match = re.search(f'{field}:\\s*(.+)', pdfinfo_output)
                if match:
                    self.metadata[field] = match.group(1).strip()
            
            # Get page count
            if 'Pages' in self.metadata:
                self.page_count = int(self.metadata['Pages'])
                logger.info(f"Found page count in metadata: {self.page_count}")
            else:
                await self._count_pages_manually()
            
            if self.page_count == 0:
                raise Exception("PDF file contains no pages")
            
            logger.info(f"PDF validation successful - Pages: {self.page_count}, Metadata: {self.metadata}")
            return self.page_count, self.metadata
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            if "Error" in error_msg:  # Only raise if actual error
                logger.error(f"pdfinfo failed: {error_msg}")
                raise Exception(f"Failed to validate PDF: {error_msg}")
            raise
        except Exception as e:
            logger.error(f"Error validating PDF: {str(e)}")
            raise

    async def _count_pages_manually(self):
        """Count pages using pdftoppm when metadata is unavailable"""
        logger.info("Page count not found in metadata, checking with pdftoppm...")
        
        # First validate PDF by trying to convert first page
        test_cmd = ['pdftoppm', '-l', '1', '-png', self.pdf_path, os.path.join(self.job_dir, 'test')]
        try:
            # Try to generate first page
            process = await asyncio.create_subprocess_exec(
                *test_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            stderr_text = stderr.decode()
            
            # Check for actual errors in stderr
            error_lines = [
                line for line in stderr_text.split('\n')
                if line and not line.startswith('pdftoppm version') and 
                   not line.startswith('Copyright') and
                   'Error' in line
            ]
            
            if process.returncode != 0 or error_lines:
                error_msg = "\n".join(error_lines) if error_lines else "Unknown error"
                raise Exception(f"Failed to generate test page: {error_msg}")
            
            # Wait for file generation
            test_file = os.path.join(self.job_dir, 'test-1.png')
            max_wait = 5  # Maximum seconds to wait
            wait_time = 0
            while not os.path.exists(test_file) and wait_time < max_wait:
                await asyncio.sleep(0.1)
                wait_time += 0.1
            
            if not os.path.exists(test_file):
                logger.error(f"Test file not found after {max_wait} seconds")
                logger.error(f"Directory contents: {os.listdir(self.job_dir)}")
                logger.error(f"Process stdout: {stdout.decode()}")
                logger.error(f"Process stderr: {stderr_text}")
                raise Exception("Test page file not found after waiting")
            
            # First page exists, now count remaining pages
            self.page_count = 1
            os.remove(test_file)  # Clean up first test file
            
            while True:
                next_page = self.page_count + 1
                test_cmd = [
                    'pdftoppm',
                    '-f', str(next_page),
                    '-l', str(next_page),
                    '-png',
                    self.pdf_path,
                    os.path.join(self.job_dir, f'test_{next_page}')
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *test_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                await process.communicate()
                
                # Wait briefly for file generation
                test_file = os.path.join(self.job_dir, f'test_{next_page}-1.png')
                await asyncio.sleep(0.1)
                
                if os.path.exists(test_file) and os.path.getsize(test_file) > 0:
                    self.page_count += 1
                    os.remove(test_file)  # Clean up test file
                else:
                    break
            
            logger.info(f"Counted {self.page_count} pages manually")
            
        except Exception as e:
            logger.error(f"Error counting pages: {str(e)}")
            raise Exception(f"Failed to validate PDF: {str(e)}")

    async def convert_to_images(self) -> List[Image.Image]:
        """Convert PDF pages to images using pdftoppm"""
        try:
            thread_count = min(multiprocessing.cpu_count(), self.page_count, config.MAX_WORKERS)
            output_prefix = os.path.join(self.job_dir, 'page')
            
            cmd = [
                'pdftoppm',
                '-png' if config.PDF_OPTIONS['png'] else '-jpeg',
                f'-r{self.dpi}',
                '-thread', str(thread_count),
                '-progress' if config.PDF_OPTIONS['progress'] else None,
                '-verbose' if config.PDF_OPTIONS['verbose'] else None,
                '-aa', 'yes' if config.PDF_OPTIONS['anti_alias'] else 'no',
                '-cropbox' if config.PDF_OPTIONS['cropbox'] else None,
                self.pdf_path,
                output_prefix
            ]
            cmd = [arg for arg in cmd if arg is not None]  # Remove None values
            
            logger.info(f"Running pdftoppm command: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout_data = []
            stderr_data = []
            
            while True:
                stdout_line = await process.stdout.readline()
                if stdout_line:
                    line = stdout_line.decode().strip()
                    stdout_data.append(line)
                    logger.info(f"pdftoppm stdout: {line}")
                
                stderr_line = await process.stderr.readline()
                if stderr_line:
                    line = stderr_line.decode().strip()
                    stderr_data.append(line)
                    if not line.startswith('pdftoppm version'):
                        logger.info(f"pdftoppm stderr: {line}")
                
                if not stdout_line and not stderr_line:
                    if process.stdout.at_eof() and process.stderr.at_eof():
                        break
                    await asyncio.sleep(0.1)
            
            return_code = await process.wait()
            
            # Check for actual errors in stderr
            error_lines = [
                line for line in stderr_data 
                if not line.startswith('pdftoppm version') and 
                   not line.startswith('Copyright') and
                   'Error' in line
            ]
            
            if return_code != 0 or error_lines:
                error_msg = "\n".join(error_lines) if error_lines else "Unknown error"
                logger.error(f"pdftoppm failed with return code {return_code}")
                logger.error(f"stdout: {stdout_data}")
                logger.error(f"stderr: {error_msg}")
                raise Exception(f"PDF conversion failed: {error_msg}")
            
            return await self._load_images(output_prefix)
            
        except Exception as e:
            logger.error(f"Error converting PDF to images: {str(e)}", exc_info=True)
            raise

    async def _load_images(self, output_prefix: str) -> List[Image.Image]:
        """Load generated PNG files into memory"""
        images = []
        for i in range(1, self.page_count + 1):
            png_path = f"{output_prefix}-{str(i).zfill(6)}.png"
            try:
                if not os.path.exists(png_path):
                    logger.error(f"Expected PNG file not found: {png_path}")
                    continue
                
                logger.info(f"Loading image {i}/{self.page_count}: {png_path}")
                with Image.open(png_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    images.append(img.copy())
                
                os.remove(png_path)
                
            except Exception as e:
                logger.error(f"Error loading image {png_path}: {str(e)}", exc_info=True)
        
        if not images:
            raise Exception(f"No images were successfully converted from the {self.page_count} page PDF")
        
        return images

    async def cleanup(self):
        """Clean up temporary files"""
        try:
            shutil.rmtree(self.job_dir)
            logger.info(f"Cleaned up temporary directory: {self.job_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up directory {self.job_dir}: {str(e)}")

    async def process(self) -> List[Image.Image]:
        """Main processing function"""
        try:
            await self.setup()
            await self.validate_pdf()
            return await self.convert_to_images()
        finally:
            await self.cleanup()
