# Directive: Fetch News & Sentiment

## Goal
Fetch recent market news and score sentiment per ticker. Primary source is Perplexity (real-time
web search + AI analysis). Alpaca News API + VADER is the fallback when Perplexity fails or
has no credits.

## Prerequisites
- `PERPLEXITY_API_KEY` in `.env` (primary)
- `PERPLEXITY_MODEL` in `.env` (default: `sonar`)
- Alpaca API key in `.env` (fallback — same as fetch_market_data.md)
- Earnings calendar: https://api.nasdaq.com/api/calendar/earnings (free, no key required)
- Install: `pip install requests vaderSentiment`

## Inputs
- `tickers`: same watchlist as fetch_market_data
- `lookback_hours`: how far back to pull news (default: 48 hours, reads `NEWS_LOOKBACK_HOURS`)
- `earnings_lookahead_days`: days ahead to check for earnings (default: 7, reads `EARNINGS_LOOKAHEAD_DAYS`)

## Script
`execution/score_sentiment.py`

## Sentiment Sources (priority order)

### 1. Perplexity sonar — Primary
- Single batched API call for all tickers (1 request per cycle, not per ticker)
- sonar model performs live web search and returns AI-synthesized sentiment
- Returns: `sentiment_label`, `sentiment_score` (-1.0 to +1.0), `earnings_near`, `headline_count`
- Output field `source: "perplexity"`
- Fails over to Alpaca + VADER on any exception (API error, parse error, no credits, timeout)

### 2. Alpaca News API + VADER — Fallback
- Fetches up to 50 headlines per batch from Alpaca's news feed
- VADER scores each headline (-1.0 to +1.0), averaged per ticker
- Earnings dates from NASDAQ calendar (free endpoint, 10s timeout, defaults to false on failure)
- Thresholds: score > 0.05 → POSITIVE, score < -0.05 → NEGATIVE, else → NEUTRAL
- Output field `source: "alpaca_vader"`

## Outputs
Returns dict `{ticker: {sentiment_score, sentiment_label, earnings_near, headline_count, source}}`
Saved to `.tmp/sentiment_{YYYY-MM-DD}.json`

## Edge Cases
- No news found for ticker (either source): default to NEUTRAL, `headline_count: 0`
- Perplexity missing a ticker in response: default to NEUTRAL, `source: "perplexity_missing"`
- NASDAQ earnings calendar slow or down: defaults to `earnings_near: false`
- Alpaca news max 50 headlines per batch request

## Earnings Proximity Penalty
- If earnings within `EARNINGS_LOOKAHEAD_DAYS` days: `earnings_near: true`
- `generate_signals.py` blocks BUY signals when `earnings_near: true`
- Reason: earnings gaps invalidate technical signals
