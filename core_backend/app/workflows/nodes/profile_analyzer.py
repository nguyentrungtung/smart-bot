import asyncio
import json
import logging
import litellm
from typing import Dict, Any
from app.workflows.state import GraphState
from app.memory.long_term import LongTermMemory
from app.config.settings import settings
from app.utils import db
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger("profile_analyzer")

_EXTRACTION_PROMPT = """\
Bạn là chuyên gia phân tích hội thoại. Nhiệm vụ của bạn là trích xuất thông tin cá nhân \
và sở thích của người dùng từ đoạn hội thoại, sau đó trả về JSON.

Chỉ trả về JSON thuần, không thêm markdown hay giải thích.

Schema:
{
  "name": "tên người dùng nếu đề cập, hoặc null",
  "new_facts": ["danh sách sự thật ngắn gọn về người dùng, tối đa 5 facts"],
  "preferences": {"key": "value pairs về sở thích nếu có"}
}

Ví dụ fact tốt: "Người dùng làm việc tại Hà Nội", "Thích cà phê đen", "Quan tâm đến lĩnh vực bất động sản"
Không tạo fact nếu không có thông tin rõ ràng. Nếu không có gì để trích xuất, trả về {"name": null, "new_facts": [], "preferences": {}}.
"""


async def profile_analyzer(state: GraphState) -> Dict[str, Any]:
    """
    Analyzes the last conversation turn to extract user facts/preferences via LLM.
    Merges extracted data into the long-term user profile in PostgreSQL.
    Runs as a terminal node — does not block the response stream.
    """
    user_id = state.get("user_id")
    messages = state.get("messages", [])

    if not user_id or not messages:
        return {}

    # Only analyze the last user+assistant exchange (last 2 messages)
    recent = messages[-2:] if len(messages) >= 2 else messages
    history_str = ""
    for m in recent:
        if isinstance(m, HumanMessage):
            role = "User"
        elif isinstance(m, AIMessage):
            role = "Assistant"
        else:
            continue
        if isinstance(m.content, str):
            text = m.content
        elif isinstance(m.content, list):
            # Extract text blocks from multimodal content (image/voice turns)
            text = " ".join(
                block.get("text", "") for block in m.content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            text = ""
        if text:
            history_str += f"{role}: {text}\n"

    if not history_str.strip():
        return {}

    # Skip trivial exchanges that cannot contain extractable profile information
    word_count = len(history_str.split())
    if word_count < 8:
        logger.info(f"LTM: Skipping profile extraction — exchange too short ({word_count} words).")
        return {}

    logger.info(f"LTM: Running LLM-based profile extraction for user {user_id}...")

    try:
        response = await asyncio.wait_for(
            litellm.acompletion(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": _EXTRACTION_PROMPT},
                    {"role": "user", "content": f"Hội thoại:\n{history_str}"}
                ],
                api_base=settings.LITELLM_API_BASE,
                api_key=settings.LITELLM_API_KEY,
                custom_llm_provider="openai",
                stream=False,
                max_tokens=512,  # Increased from 256 — some models need space for complete JSON
            ),
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

        raw = response.choices[0].message.content or ""
        # Strip markdown fences if model wraps output
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        # Extract the outermost JSON object.
        # The naive r'\{[^{}]*\}' fails on nested braces (e.g. "preferences": {}).
        # Walk character-by-character to find balanced outermost { }.
        import re
        start = raw.find("{")
        if start != -1:
            depth = 0
            end = start
            for i, ch in enumerate(raw[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            raw = raw[start:end + 1]

        extracted = json.loads(raw)

    except asyncio.TimeoutError:
        logger.warning(f"LTM: Profile extraction timed out after {settings.LLM_TIMEOUT_SECONDS}s. Skipping update.")
        return {}
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"LTM: Profile extraction failed ({type(e).__name__}: {e}). Skipping update.")
        return {}

    # Nothing useful extracted
    new_facts = extracted.get("new_facts", [])
    new_name = extracted.get("name")
    new_prefs = extracted.get("preferences", {})

    if not new_facts and not new_name and not new_prefs:
        logger.info(f"LTM: No new facts extracted for user {user_id}.")
        return {}

    pool = db.pool
    ltm = LongTermMemory(pool)
    current_profile = await ltm.get_profile(user_id) or {}

    # Merge name
    if new_name:
        current_profile["name"] = new_name

    # Merge preferences
    if new_prefs:
        existing_prefs = current_profile.get("preferences", {})
        current_profile["preferences"] = {**existing_prefs, **new_prefs}

    # Merge facts — deduplicate, keep latest 20
    existing_facts = current_profile.get("facts", [])
    merged = list(dict.fromkeys(existing_facts + new_facts))  # preserve order, dedup
    current_profile["facts"] = merged[-20:]

    await ltm.update_profile(user_id, current_profile)
    logger.info(f"LTM: Profile updated for {user_id} — {len(new_facts)} new facts, name={new_name}")

    # Invalidate Redis cache so next turn fetches fresh profile
    try:
        from app.utils.redis import get_redis
        redis = await get_redis()
        await redis.delete(f"profile_cache:{user_id}")
    except Exception:
        pass  # Cache invalidation failure is non-fatal

    return {"metadata": {**state.get("metadata", {}), "profile_synced": True}}
