from fastapi import FastAPI
from app.app.agent import BaseAgent

app = FastAPI()
agent = BaseAgent()

@app.post("/process")
async def process_chunk(chunk: str):
    result = agent.process_chunk(chunk)
    if agent.validate_result(result):
        return {"status": "success", "result": result}
    return {"status": "error", "message": "Invalid result"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/metrics")
async def metrics():
    agent.collect_metrics()
    return {"status": "metrics collected"}
