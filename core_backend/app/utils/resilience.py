import asyncio
import time
import logging
from enum import Enum
from functools import wraps
from typing import Callable, Any, Dict, Optional

logger = logging.getLogger("resilience")

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    """
    Resilient Tool Execution Wrapper (Circuit Breaker Pattern).
    Prevents cascading failures by stopping requests to failing services.
    """
    def __init__(
        self, 
        name: str, 
        failure_threshold: int = 3, 
        recovery_timeout: float = 30.0,
        expected_exception: Exception = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None

    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        logger.debug(f"Circuit [{self.name}]: Success - State={self.state}")

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit [{self.name}]: THRESHOLD REACHED - State={self.state}")
        else:
            logger.info(f"Circuit [{self.name}]: Failure ({self.failure_count}/{self.failure_threshold})")

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if time.time() - (self.last_failure_time or 0) > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info(f"Circuit [{self.name}]: Recovery timeout passed - State={self.state}")
                return True
            return False
            
        return self.state == CircuitState.HALF_OPEN

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if not self.can_execute():
            logger.warning(f"Circuit [{self.name}] is OPEN. Blocking request.")
            raise RuntimeError(f"Circuit [{self.name}] is open. Service unavailable.")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise e

def async_retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator for retrying async functions with exponential backoff.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            attempt_count = 0
            current_delay = delay
            
            while attempt_count < retries:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    attempt_count += 1
                    if attempt_count >= retries:
                        logger.error(f"Retry: Execution failed after {retries} attempts: {e}")
                        raise e
                    
                    logger.warning(
                        f"Retry: Attempt {attempt_count}/{retries} failed: {e}. "
                        f"Retrying in {current_delay:.2f}s..."
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Registry to persist state across requests in the application lifecycle
_registry: Dict[str, CircuitBreaker] = {}

def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    if name not in _registry:
        _registry[name] = CircuitBreaker(name, **kwargs)
    return _registry[name]
