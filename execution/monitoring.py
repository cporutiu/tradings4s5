import os, sys, json, logging, traceback
from datetime import datetime
from pathlib import Path

TODAY = datetime.now().strftime("%Y-%m-%d")
LOG_DIR = Path(".tmp")
LOG_DIR.mkdir(exist_ok=True)

CYCLE_LOG = LOG_DIR / f"cycle_log_{TODAY}.txt"
ERROR_LOG = LOG_DIR / "errors_latest.json"

_stream = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(CYCLE_LOG, encoding="utf-8"),
        logging.StreamHandler(_stream)
    ]
)
logger = logging.getLogger("tradingbot")

_cycle_errors = []

def log_step(step: str, status: str, message: str = ""):
    logger.info(f"{step:<28} | {status:<6} | {message}")

def log_error(step: str, exc: Exception, context: dict = None):
    tb = traceback.format_exc()
    entry = {
        "time": datetime.now().isoformat(),
        "step": step,
        "error": str(exc),
        "traceback": tb,
        "context": context or {}
    }
    _cycle_errors.append(entry)
    logger.error(f"{step:<28} | ERROR  | {exc}")
    logger.debug(tb)
    _flush_errors()

def log_warn(step: str, message: str):
    logger.warning(f"{step:<28} | WARN   | {message}")

def cycle_summary():
    status = "CLEAN" if not _cycle_errors else f"{len(_cycle_errors)} ERROR(S)"
    logger.info(f"{'CYCLE SUMMARY':<28} | {status:<6} | log -> {CYCLE_LOG}")
    if _cycle_errors:
        logger.info(f"  Error details -> {ERROR_LOG}")

def _flush_errors():
    existing = []
    if ERROR_LOG.exists():
        try:
            with open(ERROR_LOG) as f:
                existing = json.load(f)
        except Exception:
            pass
    combined = (_cycle_errors + existing)[:50]
    with open(ERROR_LOG, "w") as f:
        json.dump(combined, f, indent=2)
