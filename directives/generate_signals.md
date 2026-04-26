# Directive: Generate Signals

## Goal
Run all active strategies against the latest OHLCV bars and sentiment data.
Output a unified signal per ticker: BUY, SELL, or HOLD.

## Scripts
- `execution/compute_indicators.py` — computes all technical indicators
- `execution/strategies/s1_ema_rsi.py` through `s6_stochastic.py` — individual strategies
- `execution/regime_detector.py` — classifies market regime (TRENDING / RANGING / TRANSITION)
- `execution/candlestick_patterns.py` — bullish candle confirmation gate on BUY signals
- `execution/generate_signals.py` — runs all strategies, merges outputs, applies overrides

## Strategy Library

### S1: EMA Crossover + RSI Filter — trend following
- **Entry**: 9 EMA crosses above 21 EMA AND RSI < 70
- **Exit**: 9 EMA crosses below 21 EMA
- **Best for**: TRENDING markets, SPY/QQQ
- **Lookback needed**: 30 bars minimum
- **Regime**: TRENDING / TRANSITION

### S2: MACD + Volume Confirmation — momentum
- **Entry**: MACD line crosses above signal AND volume > 20-day avg volume
- **Exit**: MACD line crosses below signal
- **Best for**: TRENDING markets, sector ETFs (XLE, XLK)
- **Lookback needed**: 35 bars minimum
- **Regime**: TRENDING / TRANSITION

### S3: Bollinger Bands Mean Reversion — range-bound ETFs
- **Entry**: close ≤ lower BB (2 std dev, 20-day) AND RSI < 35
- **Exit**: close ≥ upper BB
- **Best for**: RANGING markets, GLD/SLV
- **Lookback needed**: 25 bars minimum
- **Regime**: RANGING / TRANSITION

### S4: SMA50 Bounce in Macro Bull — trend pullback entry
- **Macro bull filter**: SMA50 > SMA200 must be true to allow BUY
- **Entry**: price closes back above SMA50 after dipping below it (bounce signal)
- **Exit**: EMA9 crosses below EMA21 (short-term trend break) OR SMA50 < SMA200 (macro bear)
- **Best for**: TRENDING markets, large-cap ETFs (SPY, QQQ, XLF)
- **Lookback needed**: 210 bars minimum
- **Regime**: TRENDING / TRANSITION
- **Sweep result**: Sharpe 0.460 vs 0.277 baseline — strictly dominates the old golden-cross variant

### S5: RSI Dip in Uptrend — aggressive calibration
- **Uptrend filter**: close > SMA200
- **Entry**: RSI < 50 AND RSI turning up (current RSI > previous RSI)
- **Exit**: RSI > 55
- **Best for**: TRENDING markets, buying dips in bull moves
- **Lookback needed**: 210 bars minimum
- **Regime**: TRENDING / TRANSITION
- **Calibration** (`RSI_ENTRY=50`, `RSI_EXIT=55`): sweep result week 2026-04-21, Sharpe 0.612 vs 0.560 baseline, +326 trades
- **Revisit**: conservative rsi45/exit55 calibration week of 2026-05-05

### S6: Stochastic Oscillator — range trading
- **Entry**: %K crosses above %D while %K < 20 (both oversold)
- **Exit**: %K crosses below %D while %K > 80 (both overbought)
- **Best for**: RANGING markets, tight low-volatility consolidation
- **Lookback needed**: 20 bars minimum
- **Regime**: RANGING / TRANSITION

## Regime Detection (ADX-based)
ADX is computed with Wilder smoothing over 14 periods.
- ADX ≥ 25 → **TRENDING**: strategies s1, s2, s4, s5 vote
- ADX < 20 → **RANGING**: strategies s3, s6 vote
- 20 ≤ ADX < 25 → **TRANSITION**: all strategies vote

Only strategies assigned to the detected regime cast votes. Others return HOLD but are ignored in the tally.

## Signal Merging Logic
1. Each regime-active strategy votes BUY, SELL, or HOLD
2. **Regime-weighted vote**: plurality wins; if the top count = 1 and more than 1 strategy is active → HOLD (need at least 2 agreeing)
3. **Candlestick gate**: BUY signals must confirm a bullish candle pattern (hammer, engulfing, doji, etc.); unconfirmed BUY → HOLD
4. **Sentiment override** (BUY only):
   - Sentiment = NEGATIVE → downgrade to HOLD
   - `earnings_near = true` → downgrade to HOLD
   - SELL signals are never blocked (risk management priority)

## Active Strategies Config
Set in `.env`:
```
ACTIVE_STRATEGIES=s4,s5
```
Remove a strategy ID to disable without deleting code. Current config runs only trend strategies.

## Inputs
- `.tmp/bars_{YYYY-MM-DD}.json`
- `.tmp/sentiment_{YYYY-MM-DD}.json`

## Outputs
`.tmp/signals_{YYYY-MM-DD}.json`
```json
{
  "SPY": {
    "signal": "BUY",
    "raw_signal": "BUY",
    "strategy_votes": {"s4": "BUY", "s5": "HOLD"},
    "regime": "TRENDING",
    "adx": 28.5,
    "regime_active_strategies": ["s4", "s5"],
    "sentiment_label": "POSITIVE",
    "earnings_near": false,
    "candle_pattern": "hammer",
    "override_reason": ""
  }
}
```
