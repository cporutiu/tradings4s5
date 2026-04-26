import time, functools
from execution.monitoring import log_warn

TRANSIENT_KEYWORDS = [
    "rate limit", "too many requests", "timeout", "connection",
    "temporary", "503", "502", "504", "reset by peer",
    "401", "unauthorized"
]

def is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in TRANSIENT_KEYWORDS)

def retry(max_attempts: int = 3, delay_seconds: float = 5.0, step_name: str = ""):
    """Retry on transient errors with exponential backoff. Fatal errors propagate immediately."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            name = step_name or fn.__name__
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    if not is_transient(exc) or attempt == max_attempts:
                        raise
                    wait = delay_seconds * (2 ** (attempt - 1))
                    log_warn(name, f"Transient error (attempt {attempt}/{max_attempts}), retrying in {wait:.0f}s: {exc}")
                    time.sleep(wait)
        return wrapper
    return decorator
