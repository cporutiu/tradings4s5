import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from execution.monitoring import log_step, log_error, log_warn

REQUIRED_MODULES = [
    ("alpaca.data.historical", ["StockHistoricalDataClient", "NewsClient"]),
    ("alpaca.data.requests", ["StockBarsRequest", "NewsRequest"]),
    ("alpaca.data.timeframe", ["TimeFrame"]),
    ("alpaca.trading.client", ["TradingClient"]),
    ("alpaca.trading.requests", ["MarketOrderRequest", "StopOrderRequest"]),
    ("alpaca.trading.enums", ["OrderSide", "TimeInForce"]),
    ("vaderSentiment.vaderSentiment", ["SentimentIntensityAnalyzer"]),
    ("pandas", []),
    ("dotenv", []),
    ("requests", []),
    ("duckdb", []),
]

def check_imports() -> bool:
    all_ok = True
    for module_path, names in REQUIRED_MODULES:
        try:
            mod = __import__(module_path, fromlist=names)
            for name in names:
                if not hasattr(mod, name):
                    log_warn("health_check:imports", f"{module_path}.{name} not found")
                    all_ok = False
        except ImportError as e:
            log_error("health_check:imports", e, {"module": module_path})
            all_ok = False
    return all_ok

def check_env() -> bool:
    required = ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]
    all_ok = True
    for key in required:
        if not os.getenv(key):
            log_warn("health_check:env", f"{key} is missing from .env")
            all_ok = False
    if not os.getenv("PERPLEXITY_API_KEY"):
        log_warn("health_check:env", "PERPLEXITY_API_KEY not set — sentiment will fall back to Alpaca + VADER")
    return all_ok

def check_api_connectivity() -> bool:
    from alpaca.trading.client import TradingClient
    from execution.self_anneal import retry

    @retry(max_attempts=3, delay_seconds=5, step_name="health_check:api")
    def _get_account():
        client = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)
        return client.get_account()

    try:
        account = _get_account()
        log_step("health_check:api", "OK", f"Account status: {account.status} | Cash: ${float(account.cash):,.2f}")
        return True
    except Exception as e:
        log_error("health_check:api", e)
        return False

def run_health_check() -> bool:
    log_step("health_check", "START")
    imports_ok = check_imports()
    env_ok = check_env()

    if not imports_ok or not env_ok:
        log_step("health_check", "ABORT", "Fix import/env errors above before running cycle")
        return False

    api_ok = check_api_connectivity()
    if not api_ok:
        log_step("health_check", "ABORT", "API connectivity failed — check keys and network")
        return False

    log_step("health_check", "OK", "All checks passed")
    return True

if __name__ == "__main__":
    ok = run_health_check()
    sys.exit(0 if ok else 1)
