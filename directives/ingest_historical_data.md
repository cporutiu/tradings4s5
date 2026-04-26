# Directive: Ingest Historical Data (Phase 2)

## Goal
Build and maintain a local database of daily OHLCV bars for backtesting.
Enables offline strategy testing without hitting the Alpaca API repeatedly.

## Prerequisites
- Install: `pip install duckdb pandas alpaca-py`
- DuckDB chosen over SQLite for faster analytical queries on time-series data

## Scripts
- `execution/init_db.py` — creates the local DuckDB database and schema
- `execution/backfill_history.py` — one-time pull of up to 5 years of daily bars
- `execution/update_daily.py` — appends yesterday's bar each morning (step 0 in run_cycle.py)
- `execution/run_backtest.py` — runs all strategies against historical data, prints Sharpe/drawdown table
- `execution/backtest_engine.py` — simulation engine used by run_backtest.py

## Database Schema
File: `.tmp/market_data.duckdb`

```sql
CREATE TABLE bars (
    ticker      VARCHAR,
    date        DATE,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    volume      BIGINT,
    PRIMARY KEY (ticker, date)
);
```

## Backfill
- Alpaca free tier provides up to 5 years of daily bars
- Run once: `python execution/backfill_history.py`
- Takes ~2 minutes for full watchlist

## Daily Update
- Add `update_daily.py` as step 0 in `run_daily_cycle.md` once Phase 2 is active
- Only appends missing dates — safe to run multiple times (idempotent)

## Backtesting Output
`execution/run_backtest.py` outputs per-ticker and cross-ticker tables:
- Total return %, Annualized return %, Sharpe ratio, Max drawdown, Win rate, Trade count
- Recommendation: strategies with avg Sharpe < 0 across tickers → DISABLE in ACTIVE_STRATEGIES

Saved to `.tmp/backtest_results_{YYYY-MM-DD}.json`

## Phase 2 Status — ACTIVE
- [x] `init_db.py` run — DB at `.tmp/market_data.duckdb`
- [x] `backfill_history.py` run — 300 days of history per ticker
- [x] `update_daily.py` is step 0 in `run_cycle.py`
- [x] `run_backtest.py` run 2026-04-17 — recommended ACTIVE_STRATEGIES=s4,s5
- [x] `ACTIVE_STRATEGIES=s4,s5` set in `.env`
