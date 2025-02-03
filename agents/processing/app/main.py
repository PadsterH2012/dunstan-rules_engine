from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.app.agent import BaseAgent

app = FastAPI()
agent = BaseAgent()

class ChunkRequest(BaseModel):
    file_path: str
    context: Optional[Dict[str, Any]] = None

@app.post("/process")
async def process_chunk(request: ChunkRequest):
    """Process a PDF chunk using the configured AI provider"""
    try:
        result = await agent.process_chunk(request.file_path, request.context)
        return {
            "status": "success",
            "result": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Check if the service and its providers are healthy"""
    try:
        # Check if at least one provider is available
        if not agent.providers:
            return {
                "status": "unhealthy",
                "message": "No providers available"
            }
        return {
            "status": "healthy",
            "providers": list(agent.providers.keys())
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.get("/metrics")
async def metrics():
    """Get processing metrics from all providers"""
    try:
        metrics_data = agent.collect_metrics()
        return {
            "status": "success",
            "metrics": metrics_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error collecting metrics: {str(e)}")

@app.get("/providers")
async def list_providers():
    """List available providers and their configurations"""
    return {
        "default_provider": agent.default_provider,
        "available_providers": [
            {
                "name": name,
                "model": provider.model,
                "max_tokens": provider.max_tokens
            }
            for name, provider in agent.providers.items()
        ]
    }
