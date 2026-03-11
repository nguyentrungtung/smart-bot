import logging
from typing import Dict, Any
from app.workflows.state import GraphState
from app.memory.long_term import LongTermMemory
from app.utils import db 

logger = logging.getLogger("fetch_profile")

async def fetch_profile(state: GraphState) -> Dict[str, Any]:

    """
    Fetches the user's long-term profile from PostgreSQL at the start of the turn.
    Injects it into the 'metadata' to be used by the Agent.
    """
    user_id = state.get("user_id")
    if not user_id:
        return {"metadata": {**state.get("metadata", {}), "profile": {}}}

    logger.info(f"LTM: Fetching long-term profile for user {user_id}...")

    pool = db.pool

    ltm = LongTermMemory(pool)
    profile = await ltm.get_profile(user_id)
    
    if profile:
        logger.info(f"LTM: Found profile for {user_id}: {profile.get('name', 'Unknown')}")
    else:
        logger.info(f"LTM: No profile found for {user_id}")

    return {"metadata": {**state.get("metadata", {}), "profile": profile}}
