# Directive: Risk Management

## Goal
Define and enforce position sizing, stop-loss, and portfolio exposure rules.
These rules apply to every trade regardless of signal strength.

## Rules

### Position Sizing
- Max 5% of total portfolio value per position
- Formula: `shares = floor((portfolio_value * 0.05) / entry_price)`
- Never buy fractional shares (round down)

### Stop-Loss
- 2% stop-loss per trade from entry price
- Stop price = `entry_price * 0.98`
- Alpaca supports bracket orders — submit stop-loss as part of the order, not as a separate monitor
- Stop-losses are GTC (Good Till Cancelled)

### Portfolio Exposure
- Max 6 open positions at any time (6 × 5% = 30% deployed, rest in cash)
- Do not open new positions if already at max
- Prioritize BUY signals with strongest multi-strategy consensus

### Max Drawdown (Circuit Breaker)
- If total portfolio value drops >10% from its peak value: halt all new BUY orders
- Only allow SELL orders until portfolio recovers above -8% from peak
- Peak value is tracked in `.tmp/portfolio_peak.json`

### Earnings Protection
- Never open a new position within 3 days of earnings (enforced in generate_signals.md)
- Close existing positions before earnings if unrealized gain > 3% (lock in profit)

## Script
`execution/place_order.py` — all orders routed through this script, which enforces rules above

## Inputs
- Current portfolio value (from Alpaca account API)
- Signal with ticker + direction
- Current open positions

## Outputs
- Order submitted or skipped with reason logged
