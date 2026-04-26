import os, sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution.monitoring import log_step, log_error, log_warn, cycle_summary
from execution.self_anneal import retry
from execution.health_check import run_health_check
from execution.update_daily import update_daily
from execution.fetch_bars import fetch_bars
from execution.score_sentiment import score_sentiment
from execution.generate_signals import generate_signals
from execution.place_order import execute_trades
from execution.check_positions import check_positions
from execution.send_summary import send_summary

TODAY = datetime.now().strftime("%Y-%m-%d")

@retry(max_attempts=3, delay_seconds=5, step_name="fetch_bars")
def _fetch_bars():
    return fetch_bars()

@retry(max_attempts=3, delay_seconds=5, step_name="score_sentiment")
def _score_sentiment():
    return score_sentiment()

@retry(max_attempts=2, delay_seconds=3, step_name="place_order")
def _execute_trades(signals):
    return execute_trades(signals)

def run():
    log_step("CYCLE START", "INFO", f"Date: {TODAY}")

    if not run_health_check():
        cycle_summary()
        return

    # Step 0: append latest bars to local DB
    try:
        log_step("update_daily", "START")
        update_daily()
    except Exception as e:
        log_error("update_daily", e)
        log_warn("update_daily", "Continuing with existing DB data")

    # Step 1: pre-cycle position snapshot
    try:
        log_step("check_positions (pre)", "START")
        check_positions()
        log_step("check_positions (pre)", "OK")
    except Exception as e:
        log_warn("check_positions (pre)", f"Skipped — {e}")

    # Step 2: fetch bars — abort if fails
    try:
        log_step("fetch_bars", "START")
        bars = _fetch_bars()
        if not bars:
            log_step("fetch_bars", "ABORT", "No bars returned — possible market holiday")
            cycle_summary()
            return
        log_step("fetch_bars", "OK", f"{len(bars)} tickers")
    except Exception as e:
        log_error("fetch_bars", e)
        log_step("fetch_bars", "ABORT", "Cannot continue without market data")
        cycle_summary()
        return

    # Step 3: news + sentiment — degraded mode if fails
    try:
        log_step("score_sentiment", "START")
        sentiment = _score_sentiment()
        log_step("score_sentiment", "OK")
    except Exception as e:
        log_error("score_sentiment", e)
        log_warn("score_sentiment", "Defaulting to neutral sentiment for all tickers")
        sentiment = {}

    # Step 4: generate signals — abort if fails
    try:
        log_step("generate_signals", "START")
        signals = generate_signals(bars, sentiment)
        buys = sum(1 for v in signals.values() if v["signal"] == "BUY")
        sells = sum(1 for v in signals.values() if v["signal"] == "SELL")
        log_step("generate_signals", "OK", f"BUY={buys} SELL={sells} HOLD={len(signals)-buys-sells}")
    except Exception as e:
        log_error("generate_signals", e)
        log_step("generate_signals", "ABORT", "Cannot place orders without signals")
        cycle_summary()
        return

    # Step 5: execute trades
    try:
        log_step("place_order", "START")
        _execute_trades(signals)
        log_step("place_order", "OK")
    except Exception as e:
        log_error("place_order", e)

    # Step 6: post-cycle position snapshot
    positions = {}
    try:
        log_step("check_positions (post)", "START")
        check_positions()
        log_step("check_positions (post)", "OK")
        import json
        with open(f".tmp/positions_{TODAY}.json") as f:
            positions = json.load(f)
    except Exception as e:
        log_warn("check_positions (post)", f"Skipped — {e}")

    # Step 7: send email summary
    try:
        log_step("send_summary", "START")
        send_summary(signals, positions, bars, sentiment)
    except Exception as e:
        log_warn("send_summary", f"Skipped — {e}")

    cycle_summary()

if __name__ == "__main__":
    run()
