import logging
import json
import sys
import datetime
import contextvars
from typing import Any, Optional

# Context variables for tracing across async tasks
interaction_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("interaction_id", default=None)
session_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("session_id", default=None)

class JsonFormatter(logging.Formatter):
    """
    Custom formatter that outputs logs as structured JSON.
    Essential for production observability and log indexing.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "line": record.lineno,
        }
        
        # Add tracing IDs from context
        i_id = interaction_id_context.get()
        s_id = session_id_context.get()
        if i_id: log_entry["interaction_id"] = i_id
        if s_id: log_entry["session_id"] = s_id

        # Add extra attributes if present (e.g. session_id)
        if hasattr(record, "extra"):
            log_entry["extra"] = record.extra
            
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

def setup_logger(name: str = "smartbot", level: int = logging.INFO):
    """
    Configures and returns a structured JSON logger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        
    return logger

# Global default logger
logger = setup_logger()
