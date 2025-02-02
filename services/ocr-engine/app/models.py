from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, List, Optional, Annotated
from datetime import datetime

class OCRResponse(BaseModel):
    text: str
    metadata: Dict[str, Any]
    confidence: float
    processing_time: Optional[float] = None

class BatchOCRRequest(BaseModel):
    urls: List[Annotated[str, Field(pattern=r'^https?://.+\.pdf$')]] = Field(..., max_items=10)
    
    @field_validator('urls')
    @classmethod
    def validate_urls(cls, urls):
        if not urls:
            raise ValueError("At least one URL must be provided")
        return urls

class HealthCheckResponse(BaseModel):
    status: str
    version: str
    queue_size: int
    active_workers: int
    uptime: float
    last_processed: Optional[datetime] = None

class BatchOCRResponse(BaseModel):
    results: List[OCRResponse]
    failed_urls: List[str]
    job_id: str
    processing_time: float
    total_pages: int

class ProgressResponse(BaseModel):
    job_id: str
    total_pages: int
    processed_pages: int
    status: str
    progress_percentage: float
    estimated_time_remaining: Optional[float]
