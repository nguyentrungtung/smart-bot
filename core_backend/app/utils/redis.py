import redis.asyncio as redis
from app.config.settings import settings

# Global Redis Client singleton pool to be initialized
redis_pool = None

async def get_redis():
    """
    Returns an async Redis client.
    Initializes the pool if it doesn't exist.
    """
    global redis_pool
    if redis_pool is None:
        redis_pool = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_pool
