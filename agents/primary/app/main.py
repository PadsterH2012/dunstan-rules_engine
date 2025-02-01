from fastapi import FastAPI
from pydantic import BaseModel
from utils.cache import get_from_cache, set_to_cache

app = FastAPI(title="RPG Rules Engine - Primary Agent")

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    source: str
    confidence: float

@app.post("/query", response_model=QueryResponse)
async def query_rules(request: QueryRequest):
    # Normalize the query to generate a cache key.
    key = f"traveller:query:{request.query.lower().replace(' ', '_')}"
    cached_result = get_from_cache(key)
    if cached_result:
        return cached_result

    # Dummy processing: Replace with calls to OCR, NLP, and validation services.
    result = {
        "answer": "3d6",
        "source": "Traveller Core Rulebook p. 89",
        "confidence": 0.95
    }

    # Cache the result (TTL is set to 7 days)
    set_to_cache(key, result)
    return result
