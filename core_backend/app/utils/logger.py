import logging
import json
import sys
import datetime
from typing import Any

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
