import os
import base64
from typing import Dict, Any, Optional
import aiohttp
from .base import BaseProvider

class OpenAIProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        self.api_key = os.getenv("OPENAI_PROCESSING_KEY")
        self.org_id = os.getenv("OPENAI_ORG_ID")
        self.model = os.getenv("PROCESSING_DEFAULT_MODEL", "gpt-4-vision-preview")
        self.max_tokens = 2048  # Budget configuration
        self.temperature = 0.2
        self.total_tokens_used = 0
        self.total_requests = 0
        self.successful_requests = 0
        
        if not self.api_key:
            raise ValueError("OPENAI_PROCESSING_KEY environment variable is required")

    async def process_chunk(self, file_path: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process a PDF chunk using OpenAI's vision model with budget constraints"""
        try:
            # Read and encode the PDF file
            with open(file_path, "rb") as file:
                pdf_data = file.read()
                base64_pdf = base64.b64encode(pdf_data).decode('utf-8')

            # Prepare the API request
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Organization": self.org_id if self.org_id else ""
            }

            # Construct the message with budget-optimized parameters
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Extract and analyze the content from this PDF chunk. "
                        "Focus on key information and maintain high accuracy while being concise. "
                        "Format the output as structured data."
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Please analyze this PDF chunk and extract the key information:"
                        },
                        {
                            "type": "image",
                            "image_url": {
                                "url": f"data:application/pdf;base64,{base64_pdf}",
                                "detail": "low"  # Budget optimization
                            }
                        }
                    ]
                }
            ]

            # Add context if provided
            if context:
                messages[0]["content"] += f"\nContext: {context}"

            self.total_requests += 1
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                    }
                ) as response:
                    if response.status != 200:
                        error_data = await response.text()
                        raise Exception(f"OpenAI API error: {error_data}")
                    
                    result = await response.json()
                    self.successful_requests += 1
                    
                    # Update token usage
                    if "usage" in result:
                        self.total_tokens_used += result["usage"].get("total_tokens", 0)
                    
                    return {
                        "content": result["choices"][0]["message"]["content"],
                        "model": self.model,
                        "usage": result.get("usage", {}),
                        "confidence": self._calculate_confidence(result)
                    }

        except Exception as e:
            raise Exception(f"Error processing chunk with OpenAI: {str(e)}")

    def validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate the processing result"""
        try:
            # Check for required fields
            if not all(key in result for key in ["content", "model", "confidence"]):
                return False
            
            # Check content is not empty
            if not result["content"].strip():
                return False
            
            # Check confidence meets minimum threshold
            min_confidence = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))
            if result["confidence"] < min_confidence:
                return False
            
            return True
            
        except Exception:
            return False

    def get_metrics(self) -> Dict[str, Any]:
        """Get provider metrics"""
        return {
            "provider": "openai",
            "model": self.model,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "success_rate": (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0,
            "total_tokens_used": self.total_tokens_used,
            "estimated_cost": self._calculate_cost()
        }

    def _calculate_confidence(self, result: Dict[str, Any]) -> float:
        """Calculate confidence score based on response characteristics"""
        try:
            # Basic confidence calculation based on response length and model behavior
            content = result["choices"][0]["message"]["content"]
            finish_reason = result["choices"][0]["finish_reason"]
            
            # Lower confidence if response was truncated
            if finish_reason != "stop":
                return 0.6
            
            # Higher confidence for longer, more detailed responses
            content_length = len(content)
            if content_length > 1000:
                return 0.9
            elif content_length > 500:
                return 0.8
            else:
                return 0.7
                
        except Exception:
            return 0.5  # Default confidence if calculation fails

    def _calculate_cost(self) -> float:
        """Calculate estimated cost based on token usage"""
        # GPT-4 Vision pricing (as of 2024)
        cost_per_token = 0.01 / 1000  # $0.01 per 1K tokens
        return (self.total_tokens_used * cost_per_token)
