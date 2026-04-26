import os, json, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from alpaca.data.historical import NewsClient
from alpaca.data.requests import NewsRequest
from execution.monitoring import log_step, log_warn

load_dotenv()

TICKERS = os.getenv("WATCHLIST", "SPY,QQQ,GLD,SLV,XLE,XLF,XLK").split(",")
LOOKBACK_HOURS = int(os.getenv("NEWS_LOOKBACK_HOURS", "48"))
EARNINGS_LOOKAHEAD_DAYS = int(os.getenv("EARNINGS_LOOKAHEAD_DAYS", "7"))

analyzer = SentimentIntensityAnalyzer()


def fetch_sentiment_perplexity(tickers: list) -> dict:
    """Single batched call to Perplexity sonar — real-time web search, AI-scored sentiment."""
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    model = os.getenv("PERPLEXITY_MODEL", "sonar")
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY not set")

    ticker_list = ", ".join(tickers)
    prompt = (
        f"You are a financial analyst with access to live market news. "
        f"Search for recent news from the last {LOOKBACK_HOURS} hours for these tickers: {ticker_list}. "
        f"For each ticker provide: sentiment_label (POSITIVE, NEGATIVE, or NEUTRAL based on news tone), "
        f"sentiment_score (float -1.0 very bearish to +1.0 very bullish), "
        f"earnings_near (true if earnings announcement expected within {EARNINGS_LOOKAHEAD_DAYS} days, else false), "
        f"headline_count (integer, number of relevant news items found). "
        f"Respond ONLY with valid JSON, no markdown fences, no explanation. "
        f"Example: {{\"SPY\": {{\"sentiment_label\": \"NEUTRAL\", \"sentiment_score\": 0.05, "
        f"\"earnings_near\": false, \"headline_count\": 4}}}}"
    )

    resp = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        },
        timeout=90,
    )
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown code fences if the model wraps output
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(content)

    result = {}
    for ticker in tickers:
        if ticker in data:
            item = data[ticker]
            result[ticker] = {
                "sentiment_score": round(float(item.get("sentiment_score", 0.0)), 4),
                "sentiment_label": item.get("sentiment_label", "NEUTRAL"),
                "earnings_near": bool(item.get("earnings_near", False)),
                "headline_count": int(item.get("headline_count", 0)),
                "source": "perplexity",
            }
        else:
            result[ticker] = {
                "sentiment_score": 0.0,
                "sentiment_label": "NEUTRAL",
                "earnings_near": False,
                "headline_count": 0,
                "source": "perplexity_missing",
            }
    return result


def fetch_sentiment_alpaca(tickers: list) -> dict:
    """Fallback: Alpaca News API headlines scored via VADER."""
    client = NewsClient(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET_KEY")
    )
    cutoff = datetime.now() - timedelta(hours=LOOKBACK_HOURS)
    headlines = {t: [] for t in tickers}

    try:
        req = NewsRequest(symbols=",".join(tickers), start=cutoff, limit=50)
        news = client.get_news(req)
        for article in news.data.get("news", []):
            for sym in article.symbols:
                if sym in headlines:
                    headlines[sym].append(article.headline)
    except Exception as e:
        log_warn("score_sentiment", f"Alpaca news fetch failed: {e}")

    earnings_soon = _fetch_earnings_dates()

    result = {}
    for ticker in tickers:
        ticker_headlines = headlines.get(ticker, [])
        if ticker_headlines:
            scores = [analyzer.polarity_scores(h)["compound"] for h in ticker_headlines]
            avg_score = sum(scores) / len(scores)
        else:
            avg_score = 0.0
        label = "POSITIVE" if avg_score > 0.05 else "NEGATIVE" if avg_score < -0.05 else "NEUTRAL"
        result[ticker] = {
            "sentiment_score": round(avg_score, 4),
            "sentiment_label": label,
            "earnings_near": ticker in earnings_soon,
            "headline_count": len(ticker_headlines),
            "source": "alpaca_vader",
        }
    return result


def _fetch_earnings_dates() -> set:
    upcoming = set()
    try:
        today = datetime.now().date()
        url = f"https://api.nasdaq.com/api/calendar/earnings?date={today}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        for row in (resp.json().get("data", {}).get("rows") or []):
            symbol = row.get("symbol", "").upper()
            if symbol:
                upcoming.add(symbol)
    except Exception as e:
        log_warn("score_sentiment", f"Earnings calendar fetch failed: {e}")
    return upcoming


def score_sentiment(tickers=TICKERS) -> dict:
    tickers = list(tickers)

    # Primary: Perplexity real-time web search + AI sentiment
    try:
        log_step("score_sentiment", "INFO", "Trying Perplexity")
        result = fetch_sentiment_perplexity(tickers)
        source = "perplexity"
    except Exception as e:
        log_warn("score_sentiment", f"Perplexity failed ({e}) — falling back to Alpaca + VADER")
        result = fetch_sentiment_alpaca(tickers)
        source = "alpaca_vader"

    out_path = f".tmp/sentiment_{datetime.now().strftime('%Y-%m-%d')}.json"
    os.makedirs(".tmp", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    log_step("score_sentiment", "OK", f"source={source} tickers={len(result)} -> {out_path}")
    return result


if __name__ == "__main__":
    score_sentiment()
