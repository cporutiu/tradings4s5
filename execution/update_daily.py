import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import duckdb
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from execution.init_db import DB_PATH
from execution.monitoring import log_step, log_warn

load_dotenv()

TICKERS = os.getenv("WATCHLIST", "SPY,QQQ,GLD,SLV,XLE,XLF,XLK").split(",")

def update_daily():
    if not os.path.exists(DB_PATH):
        log_warn("update_daily", "DB not found — run backfill_history.py first")
        return False

    client = StockHistoricalDataClient(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET_KEY")
    )

    # fetch only the last 5 days to catch any missed bars (weekends, holidays)
    end = datetime.now()
    start = end - timedelta(days=5)

    request = StockBarsRequest(
        symbol_or_symbols=TICKERS,
        timeframe=TimeFrame.Day,
        start=start,
        end=end
    )
    bars = client.get_stock_bars(request)

    con = duckdb.connect(DB_PATH)
    total_new = 0

    for ticker in TICKERS:
        if ticker not in bars.data:
            log_warn("update_daily", f"No new bars for {ticker}")
            continue

        rows = [
            (ticker, str(bar.timestamp.date()), bar.open, bar.high, bar.low, bar.close, bar.volume)
            for bar in bars.data[ticker]
        ]

        before = con.execute("SELECT COUNT(*) FROM bars WHERE ticker = ?", [ticker]).fetchone()[0]
        con.executemany("""
            INSERT OR IGNORE INTO bars (ticker, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        after = con.execute("SELECT COUNT(*) FROM bars WHERE ticker = ?", [ticker]).fetchone()[0]
        new = after - before
        total_new += new

        if new > 0:
            log_step("update_daily", "OK", f"{ticker}: +{new} new bar(s)")

    con.close()

    if total_new == 0:
        log_step("update_daily", "OK", "DB already up to date")
    else:
        log_step("update_daily", "OK", f"Total new bars added: {total_new}")

    return True

if __name__ == "__main__":
    update_daily()
