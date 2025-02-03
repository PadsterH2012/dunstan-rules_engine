import os
import logging
from typing import Dict, Any, Optional
from ..providers.base import BaseProvider
from ..providers.openai import OpenAIProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseAgent:
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.default_provider = os.getenv("PROCESSING_DEFAULT_PROVIDER", "openai")
        self.setup_providers()

    def setup_providers(self):
        """Initialize available providers"""
        try:
            # Initialize OpenAI provider for budget-optimized processing
            self.providers["openai"] = OpenAIProvider()
            logger.info("OpenAI provider initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing OpenAI provider: {str(e)}")

    async def process_chunk(self, file_path: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process a chunk using the configured provider"""
        if not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")

        provider = self.providers.get(self.default_provider)
        if not provider:
            raise ValueError(f"Provider not found: {self.default_provider}")

        try:
            result = await provider.process_chunk(file_path, context)
            if not self.validate_result(result):
                raise ValueError("Invalid result from provider")
            return result
        except Exception as e:
            logger.error(f"Error processing chunk: {str(e)}")
            raise

    def validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate the processing result"""
        try:
            provider = self.providers.get(self.default_provider)
            if not provider:
                return False
            return provider.validate_result(result)
        except Exception as e:
            logger.error(f"Error validating result: {str(e)}")
            return False

    def collect_metrics(self) -> Dict[str, Any]:
        """Collect metrics from all providers"""
        metrics = {}
        for name, provider in self.providers.items():
            try:
                metrics[name] = provider.get_metrics()
            except Exception as e:
                logger.error(f"Error collecting metrics from {name}: {str(e)}")
                metrics[name] = {"error": str(e)}
        return metrics
