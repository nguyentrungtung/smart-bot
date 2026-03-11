import logging
from typing import Dict, Any
from app.workflows.state import GraphState
from app.memory.long_term import LongTermMemory
from app.utils import db 

logger = logging.getLogger("profile_analyzer")

async def profile_analyzer(state: GraphState) -> Dict[str, Any]:
    """
    Analyzes the conversation history to extract new user facts or preferences.
    In a real scenario, this would call an LLM to 'distill' the conversation.
    For the MVP, we simulate fact extraction and save to the long-term DB.
    """
    user_id = state.get("user_id")
    messages = state.get("messages", [])
    
    if not user_id or not messages:
        return {}

    logger.info(f"LTM: Analyzing conversation for user {user_id}...")

    # Simulating LLM extraction logic
    # In reality: extracted = await llm.extract_facts(messages)
    
    # We retrieve the current profile to merge updates
    pool = db.pool

    ltm = LongTermMemory(pool)
    current_profile = await ltm.get_profile(user_id)
    
    # Example logic: if the user mentioned a name or a preference
    # We'll just mock a new fact for demonstration
    new_facts = current_profile.get("facts", [])
    
    # Simple heuristic for the MVP:
    last_text = messages[-1].content
    if isinstance(last_text, str) and "tên tôi là" in last_text.lower():
        name = last_text.lower().split("tên tôi là")[-1].strip().split()[0]
        current_profile["name"] = name.capitalize()
        new_facts.append(f"User's name is {name.capitalize()}")

    # Deduplicate and limit facts
    current_profile["facts"] = list(set(new_facts))[:10]
    
    # Save back to Postgres
    await ltm.update_profile(user_id, current_profile)
    
    logger.info(f"LTM: Profile updated for {user_id}")
    return {"metadata": {**state.get("metadata", {}), "profile_synced": True}}
