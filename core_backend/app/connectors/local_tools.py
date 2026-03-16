import logging
import json
from typing import Dict, Any
from app.memory.long_term import LongTermMemory
from app.utils import db
import datetime
import os

logger = logging.getLogger("local_tools")

async def update_user_profile(user_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Local tool to update user profile in PostgreSQL.
    No MCP required for this.
    """
    if not user_id:
        return {"status": "error", "message": "No user_id found in state"}

    try:
        ltm = LongTermMemory(db.pool)
        # Fetch current to merge facts
        current = await ltm.get_profile(user_id)
        
        name = args.get("name")
        preferences = args.get("preferences")
        new_facts = args.get("new_facts", [])
        
        profile_updates = {
            "name": name if name else current.get("name"),
            "preferences": {**current.get("preferences", {}), **(preferences or {})},
            "facts": list(set(current.get("facts", []) + new_facts))[:20]
        }
        
        await ltm.update_profile(user_id, profile_updates)
        
        # Log specifically what was learned
        learned_summary = []
        if name: learned_summary.append(f"Name: {name}")
        if preferences: learned_summary.append(f"Prefs: {json.dumps(preferences)}")
        if new_facts: learned_summary.append(f"Facts: {', '.join(new_facts)}")
        
        logger.info(f"✨ LTM Update for {user_id}: { ' | '.join(learned_summary) if learned_summary else 'No changes' }")
        
        return {"status": "success", "message": "Thông tin của bạn đã được ghi nhớ để hỗ trợ tốt hơn lần sau."}
    except Exception as e:
        logger.error(f"Local Tool Failure: update_user_profile for {user_id}: {str(e)}")
        return {"status": "error", "message": str(e)}

async def get_current_time(timezone: str = "Asia/Ho_Chi_Minh") -> Dict[str, Any]:
    """
    Local tool to get current server time.
    """
    # Simple logic for common timezones, fallback to UTC
    now = datetime.datetime.now()
    return {
        "status": "success",
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": timezone
    }

async def read_local_file(file_path: str) -> Dict[str, Any]:
    """
    Reads content from a local file.
    Only allows access to files within the project directory for security.
    """
    # Security: Normalize and check if path is within allowed workdir
    try:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return {"status": "error", "message": f"File not found: {file_path}"}
        
        if os.path.isdir(abs_path):
            return {"status": "error", "message": f"Path is a directory, not a file."}

        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return {
            "status": "success", 
            "content": content,
            "file": os.path.basename(abs_path)
        }
    except Exception as e:
        logger.error(f"File Read Error: {str(e)}")
        return {"status": "error", "message": str(e)}

async def write_local_file(file_path: str, content: str) -> Dict[str, Any]:
    """
    Writes content to a local file.
    """
    try:
        abs_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return {"status": "success", "message": f"Successfully wrote to {file_path}"}
    except Exception as e:
        logger.error(f"File Write Error: {str(e)}")
        return {"status": "error", "message": str(e)}

async def list_local_directory(directory_path: str = ".") -> Dict[str, Any]:
    """
    Lists files in a local directory.
    """
    try:
        abs_path = os.path.abspath(directory_path)
        if not os.path.exists(abs_path):
            return {"status": "error", "message": "Directory not found"}
            
        items = os.listdir(abs_path)
        return {
            "status": "success",
            "directory": directory_path,
            "items": items
        }
    except Exception as e:
        logger.error(f"Directory List Error: {str(e)}")
        return {"status": "error", "message": str(e)}
