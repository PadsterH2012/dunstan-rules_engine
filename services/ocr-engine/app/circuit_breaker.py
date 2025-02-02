import time
from functools import wraps
from typing import Callable, Any
import logging
from . import metrics

logger = logging.getLogger(__name__)

class CircuitBreaker:
    """
    Circuit breaker pattern implementation to handle failures gracefully.
    """
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        half_open_timeout: int = 30
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_timeout = half_open_timeout
        
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
        metrics.CIRCUIT_STATE.state('closed')
    
    def can_execute(self) -> bool:
        """Check if the circuit breaker allows execution"""
        now = time.time()
        
        if self.state == "closed":
            return True
            
        if self.state == "open":
            if now - self.last_failure_time >= self.reset_timeout:
                logger.info("Circuit breaker transitioning from open to half-open")
                self.state = "half-open"
                metrics.CIRCUIT_STATE.state('half-open')
                return True
            return False
            
        # half-open state
        if now - self.last_failure_time >= self.half_open_timeout:
            return True
        return False
    
    def record_failure(self):
        """Record a failure and potentially open the circuit"""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.failures >= self.failure_threshold:
            if self.state != "open":
                logger.warning(f"Circuit breaker opened after {self.failures} failures")
                metrics.CIRCUIT_TRIPS.inc()
            self.state = "open"
            metrics.CIRCUIT_STATE.state('open')
    
    def record_success(self):
        """Record a success and potentially close the circuit"""
        self.failures = 0
        if self.state != "closed":
            logger.info("Circuit breaker closing after successful execution")
        self.state = "closed"
        metrics.CIRCUIT_STATE.state('closed')

def circuit_breaker(breaker: CircuitBreaker):
    """
    Decorator to apply circuit breaker pattern to a function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if not breaker.can_execute():
                logger.error("Circuit breaker is open, rejecting request")
                raise Exception("Service temporarily unavailable")
            
            try:
                result = await func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise
                
        return wrapper
    return decorator
