# Directive: Execute Trade

## Goal
Place, modify, or cancel orders via the Alpaca API based on signals from generate_signals.md,
subject to all rules in risk_management.md.

## Order Types Used
- **Entry**: Market order at open (submitted pre-market, executes at market open)
- **Stop-loss**: Stop order attached to entry as a bracket order (GTC)
- **Exit (signal-based)**: Market order at open when SELL signal fires

## Script
`execution/place_order.py`

## Order Flow

### BUY
1. Check risk rules (max positions, portfolio exposure, circuit breaker)
2. Calculate shares: `floor((portfolio_value * 0.05) / last_close_price)`
3. Calculate stop price: `last_close_price * 0.98`
4. Submit bracket order:
   - Leg 1: Buy X shares, market order
   - Leg 2: Stop-loss at stop_price, GTC
5. Log order to `.tmp/orders_{YYYY-MM-DD}.json`

### SELL
1. Check if position exists for ticker
2. Cancel any open stop-loss orders for this ticker
3. Submit market sell order for full position
4. Log to `.tmp/orders_{YYYY-MM-DD}.json`

### HOLD
- No action taken

## Inputs
- `.tmp/signals_{YYYY-MM-DD}.json`
- Alpaca account state (portfolio value, open positions)

## Outputs
- Orders submitted to Alpaca
- `.tmp/orders_{YYYY-MM-DD}.json` with order IDs and details

## Edge Cases
- Market is closed when cycle runs: Alpaca accepts pre-market orders — they queue and execute at open
- Insufficient buying power: skip order, log warning
- Duplicate order (already holding ticker): skip BUY, log "already in position"
- Order rejected by Alpaca: log full error response, do not retry automatically
