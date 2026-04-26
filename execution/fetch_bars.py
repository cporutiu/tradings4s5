import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import duckdb
from datetime import datetime, timedelta
from dotenv import load_dotenv
from execution.init_db import DB_PATH
from execution.monitoring import log_step, log_warn

load_dotenv()

TICKERS = os.getenv("WATCHLIST", "SPY,QQQ,GLD,SLV,XLE,XLF,XLK").split(",")
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "300"))

def fetch_bars(tickers=TICKERS, lookback_days=LOOKBACK_DAYS):
    if not os.path.exists(DB_PATH):
        log_warn("fetch_bars", "Local DB not found — run backfill_history.py first")
        return {}

    cutoff = (datetime.now() - timedelta(days=lookback_days)).date()
    con = duckdb.connect(DB_PATH, read_only=True)

    result = {}
    for ticker in tickers:
        rows = con.execute("""
            SELECT date, open, high, low, close, volume
            FROM bars
            WHERE ticker = ? AND date >= ?
            ORDER BY date ASC
        """, [ticker, cutoff]).fetchall()

        if not rows:
            log_warn("fetch_bars", f"No data in DB for {ticker} — may need backfill")
            continue

        result[ticker] = [
            {"date": str(r[0]), "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
            for r in rows
        ]

    con.close()

    out_path = f".tmp/bars_{datetime.now().strftime('%Y-%m-%d')}.json"
    os.makedirs(".tmp", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    log_step("fetch_bars", "OK", f"{len(result)} tickers | {len(next(iter(result.values())))} bars each -> {out_path}")
    return result

if __name__ == "__main__":
    fetch_bars()
