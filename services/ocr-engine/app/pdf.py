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
        self.dpi = dpi  # Use provided DPI or default from config
        self.job_dir = os.path.join(config.TEMP_DIR, str(uuid.uuid4()))
        self.pdf_path = os.path.join(self.job_dir, 'input.pdf')
        self.metadata = {}
        self.page_count = 0
        self.pdftoppm_path = '/usr/bin/pdftoppm'  # Use absolute path

    async def setup(self):
        """Initialize working directory and save PDF"""
        try:
            # Create and set permissions on job directory
            os.makedirs(self.job_dir, exist_ok=True)
            os.chmod(self.job_dir, 0o777)
            logger.info(f"Created job directory: {self.job_dir}")
            
            # Save and validate PDF content
            if not self.content or len(self.content) == 0:
                raise Exception("Empty PDF content provided")
                
            with open(self.pdf_path, 'wb') as f:
                f.write(self.content)
            os.chmod(self.pdf_path, 0o666)
            
            # Verify the PDF was saved correctly
            if not os.path.exists(self.pdf_path):
                raise Exception(f"Failed to save PDF file at {self.pdf_path}")
                
            file_size = os.path.getsize(self.pdf_path)
            if file_size == 0:
                raise Exception("Saved PDF file is empty")
                
            logger.info(f"Saved PDF file ({file_size} bytes) at {self.pdf_path}")
            logger.info(f"Job directory contents: {os.listdir(self.job_dir)}")
            
            # Verify PDF is readable
            try:
                with open(self.pdf_path, 'rb') as f:
                    header = f.read(5)
                    if header != b'%PDF-':
                        raise Exception("File does not appear to be a valid PDF (invalid header)")
            except Exception as e:
                raise Exception(f"Failed to validate PDF file: {str(e)}")
                
        except Exception as e:
            logger.error(f"Setup failed: {str(e)}")
            raise

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
        if not os.path.exists(self.pdftoppm_path):
            raise Exception(f"pdftoppm not found at {self.pdftoppm_path}")
            
        test_cmd = [
            self.pdftoppm_path,
            '-png',           # Options must come first
            '-r', '150',
            '-l', '1',
            self.pdf_path,    # Input PDF file comes after options
            os.path.join(self.job_dir, 'test')  # Output prefix comes last
        ]
        try:
            # Log the command being executed
            logger.info(f"Executing pdftoppm command: {' '.join(test_cmd)}")
            
            # Try to generate first page
            process = await asyncio.create_subprocess_exec(
                *test_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            stdout_text = stdout.decode()
            stderr_text = stderr.decode()
            
            # Log command output
            if stdout_text:
                logger.info(f"pdftoppm stdout: {stdout_text}")
            if stderr_text:
                logger.info(f"pdftoppm stderr: {stderr_text}")
                
            # Log the expected output file path
            test_file = os.path.join(self.job_dir, 'test-1.png')  # Standard pdftoppm output format
            logger.info(f"Expecting output file at: {test_file}")
            
            # Log the job directory contents before waiting
            logger.info(f"Job directory contents before wait: {os.listdir(self.job_dir)}")
            
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
            
            # Wait for file generation with periodic checks
            max_wait = 15  # Further increased maximum seconds to wait
            wait_time = 0
            found_file = None
            
            while wait_time < max_wait:
                await asyncio.sleep(0.5)  # Longer sleep interval
                wait_time += 0.5
                
                # Log directory contents every second
                if wait_time % 1 == 0:
                    contents = os.listdir(self.job_dir)
                    logger.info(f"Job directory contents at {wait_time}s: {contents}")
                    
                    # Look for any PNG file that might be our output
                    png_files = [f for f in contents if f.endswith('.png')]
                    if png_files:
                        found_file = os.path.join(self.job_dir, png_files[0])
                        break
            
            if found_file:
                # If we found a PNG file, use it regardless of its name
                test_file = found_file
                os.chmod(test_file, 0o666)
                logger.info(f"File found and permissions set: {test_file}")
                logger.info(f"File size: {os.path.getsize(test_file)} bytes")
            else:
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
                    self.pdftoppm_path,
                    '-png',           # Options must come first
                    '-r', '150',
                    '-f', str(next_page),
                    '-l', str(next_page),
                    self.pdf_path,    # Input PDF file comes after options
                    os.path.join(self.job_dir, f'test_{next_page}')  # Output prefix comes last
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *test_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                await process.communicate()
                
                # Wait for file generation and check for any new PNG files
                await asyncio.sleep(0.5)  # Increased wait time
                
                # Get current PNG files
                contents = os.listdir(self.job_dir)
                png_files = [f for f in contents if f.endswith('.png')]
                
                if png_files:
                    test_file = os.path.join(self.job_dir, png_files[0])
                    if os.path.exists(test_file) and os.path.getsize(test_file) > 0:
                        os.chmod(test_file, 0o666)
                        self.page_count += 1
                        os.remove(test_file)  # Clean up test file
                        logger.info(f"Found page {self.page_count}")
                    else:
                        break
                else:
                    # No PNG file found, means we've reached the end
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
                self.pdftoppm_path,
                '-png',               # Options must come first
                '-r', str(self.dpi),
                self.pdf_path,        # Input PDF file comes after options
                output_prefix         # Output prefix comes last
            ]
            
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
            
            # Log all output for debugging
            logger.info("pdftoppm process completed")
            logger.info(f"Return code: {return_code}")
            logger.info(f"Full stdout: {stdout_data}")
            logger.info(f"Full stderr: {stderr_data}")
            
            # Check for actual errors in stderr
            error_lines = [
                line for line in stderr_data 
                if line and not line.startswith('pdftoppm version') and 
                   not line.startswith('Copyright')
            ]
            
            if return_code != 0:
                error_msg = "\n".join(error_lines) if error_lines else f"Process failed with return code {return_code}"
                logger.error(f"pdftoppm failed: {error_msg}")
                raise Exception(f"PDF conversion failed: {error_msg}")
            
            if error_lines:
                logger.warning(f"pdftoppm warnings: {error_lines}")
            
            # Wait for file generation with periodic checks
            max_wait = 60  # Even longer wait time for full conversion
            wait_time = 0
            found_files = []
            last_count = 0
            
            logger.info(f"Starting to wait for {self.page_count} pages to be generated")
            while wait_time < max_wait:
                await asyncio.sleep(2.0)  # Longer sleep interval for batch processing
                wait_time += 2.0
                
                try:
                    # Get current PNG files
                    contents = os.listdir(self.job_dir)
                    logger.info(f"Job directory contents at {wait_time}s: {contents}")
                    
                    # Look for PNG files with standard pdftoppm naming
                    png_files = sorted([f for f in contents if f.endswith('.png') and f.startswith('page-')])
                    current_count = len(png_files)
                    
                    if current_count > last_count:
                        logger.info(f"Found {current_count} pages out of {self.page_count}")
                        last_count = current_count
                        
                        # Set permissions on new files
                        for png_file in png_files[len(found_files):]:
                            file_path = os.path.join(self.job_dir, png_file)
                            if os.path.exists(file_path):
                                try:
                                    os.chmod(file_path, 0o666)
                                    found_files.append(file_path)
                                    logger.info(f"Added file: {file_path}")
                                except Exception as e:
                                    logger.error(f"Error setting permissions on {file_path}: {str(e)}")
                    
                    # If we have all expected pages, we're done
                    if current_count >= self.page_count:
                        logger.info(f"Found all {self.page_count} pages")
                        break
                        
                    # If no new files in a while, check if process is still running
                    if wait_time > 10 and current_count == 0:
                        logger.warning("No files generated after 10 seconds")
                        
                except Exception as e:
                    logger.error(f"Error checking directory contents: {str(e)}")
            
            if not found_files:
                logger.error(f"No PNG files found after {max_wait} seconds")
                logger.error(f"Final directory contents: {os.listdir(self.job_dir)}")
                raise Exception("PDF conversion failed: No output files generated")
            
            if len(found_files) < self.page_count:
                logger.warning(f"Only found {len(found_files)} pages out of {self.page_count}")
            
            # Load images from the files we found
            images = []
            for file_path in sorted(found_files):
                try:
                    logger.info(f"Loading image: {file_path}")
                    with Image.open(file_path) as img:
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        images.append(img.copy())
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error loading image {file_path}: {str(e)}")
            
            if not images:
                raise Exception(f"No images were successfully converted from the {self.page_count} page PDF")
            
            return images
            
        except Exception as e:
            logger.error(f"Error converting PDF to images: {str(e)}", exc_info=True)
            raise

    async def cleanup(self):
        """Clean up temporary files"""
        try:
            if os.path.exists(self.job_dir):
                # Log directory contents before cleanup
                logger.info(f"Directory contents before cleanup: {os.listdir(self.job_dir)}")
                shutil.rmtree(self.job_dir)
                logger.info(f"Cleaned up temporary directory: {self.job_dir}")
            else:
                logger.info(f"Job directory {self.job_dir} already removed")
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
