# Directive: Manage Positions

## Goal
Report current open positions, unrealized P&L, and update the portfolio peak tracker.

## Script
`execution/check_positions.py`

## What It Does
1. Pulls all open positions from Alpaca account API
2. Calculates unrealized P&L per position and total
3. Updates `.tmp/portfolio_peak.json` if current value > stored peak
4. Flags any positions approaching stop-loss (within 0.5% of stop price)
5. Flags positions with earnings in next 3 days (cross-reference sentiment data)
6. Prints summary to console / logs to `.tmp/positions_{YYYY-MM-DD}.json`

## Outputs
Console summary:
```
Portfolio Value: $102,450  | Peak: $104,200 | Drawdown: -1.7%
Open Positions (4/6):
  SPY  | 12 shares | Entry: $510.20 | Current: $518.40 | P&L: +$98.40 (+1.6%)
  GLD  |  5 shares | Entry: $215.00 | Current: $208.10 | P&L: -$34.50 (-3.2%) ⚠ NEAR STOP
  QQQ  |  8 shares | Entry: $432.00 | Current: $445.20 | P&L: +$105.60 (+3.1%)
  XLE  | 15 shares | Entry: $89.50  | Current: $91.20  | P&L: +$25.50 (+1.9%)
```

## Inputs
- Alpaca account API (live positions)
- `.tmp/portfolio_peak.json`

## Edge Cases
- No open positions: log "No open positions" and exit cleanly
- Alpaca API down: log error, skip position check, do not halt cycle
