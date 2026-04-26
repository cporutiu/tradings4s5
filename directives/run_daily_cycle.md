# Directive: Run Daily Cycle

## Goal
Master orchestrator. Runs once daily before market open (8:30 AM ET recommended).
Executes all steps in order, logs results, handles errors gracefully.

## Schedule
- **When**: 8:30 AM ET, Monday–Friday
- **Why 8:30 AM**: market opens at 9:30 AM ET, giving 60 min buffer for order submission
- **Skip**: US market holidays (Alpaca API returns empty bars — detect and exit early)

## Script
`execution/run_cycle.py`

## Execution Order
```
0. update_daily.py          — append yesterday's bar to local DuckDB (idempotent)
1. check_positions.py       — snapshot current state before doing anything
2. fetch_bars.py            — get latest OHLCV data from Alpaca
3. score_sentiment.py       — news + earnings sentiment (Perplexity primary, Alpaca+VADER fallback)
4. generate_signals.py      — compute indicators, run strategies, merge signals
5. place_order.py           — execute trades based on signals + risk rules
6. check_positions.py       — snapshot state after trades (confirms orders submitted)
7. send_summary.py          — email daily summary with signals, positions, portfolio value
```

## Logging
- Each step logs to `.tmp/cycle_log_{YYYY-MM-DD}.txt`
- Format: `[HH:MM:SS] STEP | STATUS | message`
- On any step failure: log error, skip remaining steps, do not crash silently

## How to Run Manually
```bash
cd "c:/Users/Cipru/OneDrive - Picksur LLC/Documents/AIPROJECTS/TradingBot"
python execution/run_cycle.py
```

## How to Schedule (Windows Task Scheduler)
1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily at 8:30 AM
3. Action: Start a program
   - Program: `python`
   - Arguments: `execution/run_cycle.py`
   - Start in: `c:/Users/Cipru/OneDrive - Picksur LLC/Documents/AIPROJECTS/TradingBot`
4. Conditions: uncheck "Start only if computer is on AC power" if on laptop

## Market Holiday Detection
- If Alpaca returns no bars for any ticker on a weekday → assume market holiday → log and exit
- Do not submit orders on holidays

## Error Handling Philosophy
- Step fails → log error + continue to next step where possible
- Exception: if fetch_bars fails → abort cycle (no data = no signals = no trades)
- Never let an unhandled exception silently skip order submission
