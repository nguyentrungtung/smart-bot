import logging
import json
from typing import Dict, Any
from app.memory.long_term import LongTermMemory
from app.utils import db
import datetime
import os

logger = logging.getLogger("local_tools")

# Sandbox: all file tool operations are restricted to this directory.
# Override via FILE_TOOL_ALLOWED_DIR env var for deployment.
_ALLOWED_BASE = os.path.realpath(
    os.environ.get("FILE_TOOL_ALLOWED_DIR", "/app/data/user_files")
)


def _safe_path(path: str) -> str:
    """
    Resolve path relative to _ALLOWED_BASE and reject any path that escapes it.
    Raises PermissionError on path traversal attempts.
    """
    # Join with base so relative paths stay sandboxed; realpath resolves symlinks
    resolved = os.path.realpath(os.path.join(_ALLOWED_BASE, path))
    if not resolved.startswith(_ALLOWED_BASE + os.sep) and resolved != _ALLOWED_BASE:
        raise PermissionError(f"Path traversal rejected: {path!r}")
    return resolved

async def update_user_profile(user_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Local tool to update user profile in PostgreSQL.
    No MCP required for this.
    """
    if not user_id:
        return {"code": 401, "status": "error", "message": "No user_id found in state"}

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
        
        return {"code": 200, "status": "success", "message": "Thông tin của bạn đã được ghi nhớ để hỗ trợ tốt hơn lần sau."}
    except Exception as e:
        logger.error(f"Local Tool Failure: update_user_profile for {user_id}: {str(e)}")
        return {"code": 500, "status": "error", "message": str(e)}

async def get_current_time(timezone: str = "Asia/Ho_Chi_Minh") -> Dict[str, Any]:
    """
    Local tool to get current server time.
    """
    # Simple logic for common timezones, fallback to UTC
    now = datetime.datetime.now()
    return {
        "code": 200,
        "status": "success",
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": timezone
    }

async def read_local_file(file_path: str) -> Dict[str, Any]:
    """
    Reads content from a local file sandboxed to _ALLOWED_BASE.
    """
    try:
        abs_path = _safe_path(file_path)
        if not os.path.exists(abs_path):
            return {"code": 404, "status": "error", "message": f"File not found: {file_path}"}
        if os.path.isdir(abs_path):
            return {"code": 400, "status": "error", "message": "Path is a directory, not a file."}
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"code": 200, "status": "success", "content": content, "file": os.path.basename(abs_path)}
    except PermissionError as e:
        logger.warning(f"File Read BLOCKED (path traversal): {e}")
        return {"code": 403, "status": "error", "message": "Access denied: path not allowed."}
    except Exception as e:
        logger.error(f"File Read Error: {str(e)}")
        return {"code": 500, "status": "error", "message": str(e)}

async def write_local_file(file_path: str, content: str) -> Dict[str, Any]:
    """
    Writes content to a local file sandboxed to _ALLOWED_BASE.
    """
    try:
        abs_path = _safe_path(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"code": 200, "status": "success", "message": f"Successfully wrote to {file_path}"}
    except PermissionError as e:
        logger.warning(f"File Write BLOCKED (path traversal): {e}")
        return {"code": 403, "status": "error", "message": "Access denied: path not allowed."}
    except Exception as e:
        logger.error(f"File Write Error: {str(e)}")
        return {"code": 500, "status": "error", "message": str(e)}

async def list_local_directory(directory_path: str = ".") -> Dict[str, Any]:
    """
    Lists files in a local directory sandboxed to _ALLOWED_BASE.
    """
    try:
        abs_path = _safe_path(directory_path)
        if not os.path.exists(abs_path):
            return {"code": 404, "status": "error", "message": "Directory not found"}
        items = os.listdir(abs_path)
        return {"code": 200, "status": "success", "directory": directory_path, "items": items}
    except PermissionError as e:
        logger.warning(f"Directory List BLOCKED (path traversal): {e}")
        return {"code": 403, "status": "error", "message": "Access denied: path not allowed."}
    except Exception as e:
        logger.error(f"Directory List Error: {str(e)}")
        return {"code": 500, "status": "error", "message": str(e)}
