import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import duckdb
from execution.monitoring import log_step

DB_PATH = ".tmp/market_data.duckdb"

def init_db():
    os.makedirs(".tmp", exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS bars (
            ticker  VARCHAR,
            date    DATE,
            open    DOUBLE,
            high    DOUBLE,
            low     DOUBLE,
            close   DOUBLE,
            volume  BIGINT,
            PRIMARY KEY (ticker, date)
        )
    """)
    con.close()
    log_step("init_db", "OK", f"Database ready -> {DB_PATH}")

if __name__ == "__main__":
    init_db()
