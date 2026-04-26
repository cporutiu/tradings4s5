import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import duckdb
from datetime import datetime, timedelta
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from execution.init_db import init_db, DB_PATH
from execution.monitoring import log_step, log_warn

load_dotenv()

TICKERS = os.getenv("WATCHLIST", "SPY,QQQ,GLD,SLV,XLE,XLF,XLK").split(",")
BACKFILL_YEARS = 5

def backfill():
    init_db()

    client = StockHistoricalDataClient(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET_KEY")
    )

    end = datetime.now()
    start = end - timedelta(days=365 * BACKFILL_YEARS)

    log_step("backfill", "START", f"{BACKFILL_YEARS} years for {TICKERS}")

    request = StockBarsRequest(
        symbol_or_symbols=TICKERS,
        timeframe=TimeFrame.Day,
        start=start,
        end=end
    )
    bars = client.get_stock_bars(request)

    con = duckdb.connect(DB_PATH)
    total = 0

    for ticker in TICKERS:
        if ticker not in bars.data:
            log_warn("backfill", f"No data returned for {ticker}")
            continue

        rows = [
            (ticker, str(bar.timestamp.date()), bar.open, bar.high, bar.low, bar.close, bar.volume)
            for bar in bars.data[ticker]
        ]

        con.executemany("""
            INSERT OR IGNORE INTO bars (ticker, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)

        count = con.execute("SELECT COUNT(*) FROM bars WHERE ticker = ?", [ticker]).fetchone()[0]
        log_step("backfill", "OK", f"{ticker}: {len(rows)} bars inserted | total stored: {count}")
        total += len(rows)

    con.close()
    log_step("backfill", "DONE", f"Total bars stored: {total} -> {DB_PATH}")

if __name__ == "__main__":
    backfill()
