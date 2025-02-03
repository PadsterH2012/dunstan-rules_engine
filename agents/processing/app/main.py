from fastapi import FastAPI
from app.app.agent import BaseAgent

app = FastAPI()
agent = BaseAgent()

from pydantic import BaseModel
from typing import Dict

class ChunkRequest(BaseModel):
    job_id: str
    chunk_id: str
    file_path: str
    page_range: Dict[str, int]

@app.post("/process")
async def process_chunk(request: ChunkRequest):
    try:
        result = agent.process_chunk(request.file_path)
        if agent.validate_result(result):
            return {
                "status": "success",
                "result": result,
                "page_range": request.page_range
            }
        return {"status": "error", "message": "Invalid result"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/metrics")
async def metrics():
    agent.collect_metrics()
    return {"status": "metrics collected"}
