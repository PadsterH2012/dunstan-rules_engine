import os
import redis
import json

# Connect to Redis using environment variables; defaults are provided.
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

def get_from_cache(key: str):
    """Retrieve a value from Redis and decode the JSON."""
    value = redis_client.get(key)
    if value:
        return json.loads(value)
    return None

def set_to_cache(key: str, value: dict, ttl: int = 604800):
    """Store a value in Redis with a TTL (default 7 days)."""
    redis_client.setex(key, ttl, json.dumps(value))
