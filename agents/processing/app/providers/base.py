from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseProvider(ABC):
    """Base class for AI providers"""
    
    @abstractmethod
    async def process_chunk(self, file_path: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a PDF chunk and return the results
        
        Args:
            file_path: Path to the PDF chunk file
            context: Optional context information for processing
            
        Returns:
            Dict containing:
                - content: Extracted/processed content
                - model: Model used for processing
                - usage: Resource usage statistics
                - confidence: Confidence score (0-1)
        """
        pass

    @abstractmethod
    def validate_result(self, result: Dict[str, Any]) -> bool:
        """
        Validate the processing result
        
        Args:
            result: The result to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        pass

    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get provider metrics
        
        Returns:
            Dict containing provider-specific metrics
        """
        pass
