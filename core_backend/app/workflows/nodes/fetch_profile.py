import json
import logging
import random
from typing import Dict, Any
from app.workflows.state import GraphState
from app.memory.long_term import LongTermMemory
from app.utils import db

logger = logging.getLogger("fetch_profile")

_PROFILE_CACHE_TTL = 300  # 5 minutes base — jitter applied below to avoid thundering herd
_PROFILE_CACHE_JITTER = 30  # ±30s randomization


async def fetch_profile(state: GraphState) -> Dict[str, Any]:
    """
    Fetches the user's long-term profile from PostgreSQL at the start of the turn.
    Caches the result in Redis for 5 minutes to avoid a DB hit on every message.
    Injects profile into 'metadata' for use by the Agent and Guard nodes.
    """
    user_id = state.get("user_id")
    if not user_id:
        return {"metadata": {"profile": {}}}

    cache_key = f"profile_cache:{user_id}"
    redis = None

    # 1. Try Redis cache first
    try:
        from app.utils.redis import get_redis
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached:
            profile = json.loads(cached)
            logger.info(f"LTM: Cache HIT for user {user_id} ({profile.get('name', 'unknown')})")
            return {"metadata": {"profile": profile}}
    except Exception as e:
        logger.warning(f"LTM: Redis cache unavailable ({e}). Falling back to DB.")

    # 2. DB lookup
    logger.info(f"LTM: Cache MISS — fetching profile from DB for user {user_id}...")
    ltm = LongTermMemory(db.pool)
    profile = await ltm.get_profile(user_id) or {}

    if profile:
        logger.info(f"LTM: Found profile for {user_id}: {profile.get('name', 'Unknown')}, {len(profile.get('facts', []))} facts")
    else:
        logger.info(f"LTM: No profile found for {user_id}, using empty profile.")

    # 3. Write back to Redis cache with jitter to avoid thundering herd
    if redis is not None:
        try:
            ttl = _PROFILE_CACHE_TTL + random.randint(-_PROFILE_CACHE_JITTER, _PROFILE_CACHE_JITTER)
            await redis.set(cache_key, json.dumps(profile), ex=ttl)
        except Exception:
            pass  # Cache write failure is non-fatal

    return {"metadata": {"profile": profile}}
