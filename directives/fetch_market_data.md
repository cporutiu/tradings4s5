# Directive: Fetch Market Data

## Goal
Pull OHLCV (Open, High, Low, Close, Volume) daily bars from Alpaca for the target ETF watchlist.

## Prerequisites (First-Time Setup)
1. Create a free Alpaca account at https://alpaca.markets
2. Go to Paper Trading → API Keys → Generate new key
3. Copy `API Key ID` and `Secret Key` into `.env`:
   ```
   ALPACA_API_KEY=your_key_id
   ALPACA_SECRET_KEY=your_secret_key
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ```
4. Install dependencies: `pip install alpaca-py python-dotenv`

## Inputs
- `tickers`: list of ETF symbols (default watchlist below)
- `lookback_days`: number of calendar days of history to fetch (default: 60)

## Default Watchlist
- SPY, QQQ — broad market
- GLD, SLV — commodity exposure
- XLE, XLF, XLK, XLV, XLU, XLI — sector rotation
- IWM — small caps
- HYG — high yield credit
- EEM — emerging markets
- SOXX — semiconductors

Full list in `.env`: `WATCHLIST=SPY,QQQ,GLD,SLV,XLE,XLF,XLK,XLV,XLU,XLI,IWM,HYG,EEM,SOXX`

## Script
`execution/fetch_bars.py`

## Outputs
Returns a dict of `{ticker: DataFrame}` with columns: `open, high, low, close, volume, timestamp`
Saved to `.tmp/bars_{YYYY-MM-DD}.json`

## Edge Cases
- Market holidays: Alpaca returns no bar for that day — this is expected, do not treat as error
- After-hours: use only daily bars (timeframe=1Day), not intraday
- Rate limits: Alpaca free tier allows 200 requests/min — well within daily cycle needs

## Notes
- Always use paper trading URL during development and testing
- Switch to `https://api.alpaca.markets` only when going live with real money
