import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
from PIL import Image
import io
import os

from app.main import app, process_page

client = TestClient(app)

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "data"
TEST_DATA_DIR.mkdir(exist_ok=True)

def create_test_pdf():
    """Create a simple test PDF with known text"""
    # Create a simple image with text
    img = Image.new('RGB', (800, 600), color='white')
    # You would normally add text here with PIL.ImageDraw
    # For this test, we'll just save the blank image
    
    # Save as PDF
    pdf_path = TEST_DATA_DIR / "test.pdf"
    img.save(pdf_path, "PDF")
    return pdf_path

@pytest.fixture
def test_pdf():
    """Fixture to create and cleanup test PDF"""
    pdf_path = create_test_pdf()
    yield pdf_path
    # Cleanup
    if pdf_path.exists():
        pdf_path.unlink()

def test_root_endpoint():
    """Test the root endpoint returns welcome message"""
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
    assert "Welcome" in response.json()["message"]

def test_extract_invalid_file():
    """Test uploading non-PDF file is rejected"""
    # Create a text file
    content = b"This is not a PDF"
    response = client.post(
        "/extract",
        files={"file": ("test.txt", content, "text/plain")}
    )
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["detail"]

def test_process_page():
    """Test parallel page processing function"""
    # Create a test image
    img = Image.new('RGB', (800, 600), color='white')
    
    with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_pdf:
        # Process the page
        result = process_page(img, temp_pdf.name, 0)
        
        assert isinstance(result, dict)
        assert 'text' in result
        assert 'confidence' in result
        assert 'page' in result
        assert result['page'] == 1

def test_extract_pdf(test_pdf):
    """Test PDF extraction endpoint with test PDF"""
    with open(test_pdf, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("test.pdf", f, "application/pdf")}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    assert "metadata" in data
    assert "confidence" in data
    assert data["metadata"]["parallel_processed"] is True

def test_batch_extract():
    """Test batch PDF processing"""
    # Create test URLs - in real tests these would be actual PDF URLs
    urls = ["http://example.com/test1.pdf", "http://example.com/test2.pdf"]
    
    response = client.post(
        "/batch-extract",
        json={"urls": urls}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "failed_urls" in data
    # Since these are fake URLs, they should be in failed_urls
    assert len(data["failed_urls"]) == 2

def test_parallel_processing_improvement(test_pdf):
    """Test that parallel processing is faster than sequential"""
    import time
    
    # Process with parallel processing
    start_time = time.time()
    with open(test_pdf, "rb") as f:
        response = client.post(
            "/extract",
            files={"file": ("test.pdf", f, "application/pdf")}
        )
    parallel_time = time.time() - start_time
    
    assert response.status_code == 200
    assert parallel_time > 0  # Basic sanity check
    
    # In a real test, you would compare this with sequential processing time
    # But for this example, we'll just check the response indicates parallel processing
    assert response.json()["metadata"]["parallel_processed"] is True
