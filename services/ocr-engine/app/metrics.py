from prometheus_client import Counter, Histogram, Gauge, Enum
import time

# Batch processing metrics
BATCH_JOBS_TOTAL = Counter(
    'ocr_batch_jobs_total',
    'Total number of batch jobs processed'
)

BATCH_URLS_TOTAL = Counter(
    'ocr_batch_urls_total',
    'Total number of URLs in all batch jobs'
)

BATCH_PROCESSING_TIME = Histogram(
    'ocr_batch_processing_seconds',
    'Time spent processing batch jobs',
    buckets=(10, 30, 60, 120, 300, 600, 1800, 3600)
)

# Retry metrics
RETRY_ATTEMPTS = Counter(
    'ocr_retry_attempts_total',
    'Total number of retry attempts',
    ['status_code']
)

RETRY_SUCCESS = Counter(
    'ocr_retry_success_total',
    'Total number of successful retries'
)

# Circuit breaker metrics
CIRCUIT_STATE = Enum(
    'ocr_circuit_breaker_state',
    'Current state of the circuit breaker',
    states=['closed', 'open', 'half-open']
)

CIRCUIT_TRIPS = Counter(
    'ocr_circuit_breaker_trips_total',
    'Total number of times the circuit breaker has tripped'
)

# Progress tracking metrics
JOBS_IN_PROGRESS = Gauge(
    'ocr_jobs_in_progress',
    'Number of jobs currently being processed'
)

TOTAL_PROGRESS_PERCENT = Gauge(
    'ocr_total_progress_percent',
    'Overall progress percentage of current jobs',
    ['job_id']
)

# Existing counters for tracking total operations
TOTAL_PDFS_PROCESSED = Counter(
    'ocr_pdfs_processed_total',
    'Total number of PDFs processed'
)

TOTAL_PAGES_PROCESSED = Counter(
    'ocr_pages_processed_total',
    'Total number of pages processed'
)

FAILED_PDFS = Counter(
    'ocr_pdfs_failed_total',
    'Total number of PDFs that failed processing'
)

# Histograms for timing
PDF_PROCESSING_TIME = Histogram(
    'ocr_pdf_processing_seconds',
    'Time spent processing PDFs',
    buckets=(1, 5, 10, 30, 60, 120, 300, 600)
)

PAGE_PROCESSING_TIME = Histogram(
    'ocr_page_processing_seconds',
    'Time spent processing individual pages',
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30)
)

# Performance metrics
PARALLEL_WORKERS = Gauge(
    'ocr_parallel_workers',
    'Number of parallel worker processes'
)

QUEUE_CAPACITY = Gauge(
    'ocr_queue_capacity_percent',
    'Percentage of queue capacity used'
)

# System state gauges
ACTIVE_WORKERS = Gauge(
    'ocr_active_workers',
    'Number of currently active worker processes'
)

QUEUE_SIZE = Gauge(
    'ocr_queue_size',
    'Number of items in the processing queue'
)

CACHE_SIZE = Gauge(
    'ocr_cache_size',
    'Number of items in the cache'
)

# Cache metrics
CACHE_HITS = Counter(
    'ocr_cache_hits_total',
    'Total number of cache hits'
)

CACHE_MISSES = Counter(
    'ocr_cache_misses_total',
    'Total number of cache misses'
)

class MetricsTimer:
    """Context manager for timing operations"""
    def __init__(self, metric):
        self.metric = metric
        
    def __enter__(self):
        self.start = time.time()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start
        self.metric.observe(duration)
