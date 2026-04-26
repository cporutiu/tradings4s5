import os, json, importlib, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime
from dotenv import load_dotenv
from execution.candlestick_patterns import bullish_confirmation
from execution.regime_detector import detect_regime, active_strategies_for_regime
from execution.constants import STRATEGY_MODULE_MAP
from execution.monitoring import log_step, log_warn

load_dotenv()

ACTIVE_STRATEGIES = os.getenv("ACTIVE_STRATEGIES", "s1,s2,s3,s4,s5,s6").split(",")

def regime_weighted_vote(votes: dict, regime_active: set) -> str:
    counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
    active_count = sum(1 for sid in votes if sid in regime_active)
    for sid, vote in votes.items():
        if sid in regime_active:
            counts[vote] = counts.get(vote, 0) + 1
    if active_count == 0:
        return "HOLD"
    top = max(counts, key=counts.get)
    return "HOLD" if counts[top] == 1 and active_count > 1 else top

def _sentiment_override(signal: str, sentiment: dict) -> tuple[str, str]:
    if signal == "BUY":
        if sentiment.get("sentiment_label") == "NEGATIVE":
            return "HOLD", "negative sentiment"
        if sentiment.get("earnings_near"):
            return "HOLD", "earnings within 3 days"
    return signal, ""

def generate_signals(bars: dict, sentiment: dict) -> dict:
    strategies = {}
    for sid in ACTIVE_STRATEGIES:
        path = STRATEGY_MODULE_MAP.get(sid)
        if not path:
            log_warn("generate_signals", f"Unknown strategy id: {sid}")
            continue
        strategies[sid] = importlib.import_module(path)

    result = {}
    for ticker, ticker_bars in bars.items():
        regime, adx_val = detect_regime(ticker_bars)
        regime_active = active_strategies_for_regime(regime, list(strategies.keys()))

        votes = {}
        for sid, mod in strategies.items():
            try:
                votes[sid] = mod.run(ticker_bars)
            except Exception as e:
                log_warn("generate_signals", f"Strategy {sid} failed for {ticker}: {e}")
                votes[sid] = "HOLD"

        raw_signal = regime_weighted_vote(votes, regime_active)

        ticker_sentiment = sentiment.get(ticker, {"sentiment_label": "NEUTRAL", "earnings_near": False})
        signal, override_reason = _sentiment_override(raw_signal, ticker_sentiment)

        candle_pattern = ""
        if signal == "BUY":
            confirmed, pattern = bullish_confirmation(ticker_bars)
            if confirmed:
                candle_pattern = pattern
            else:
                signal, override_reason = "HOLD", f"no bullish candle ({pattern})"

        result[ticker] = {
            "signal": signal,
            "raw_signal": raw_signal,
            "strategy_votes": votes,
            "regime": regime,
            "adx": adx_val,
            "regime_active_strategies": sorted(regime_active),
            "sentiment_label": ticker_sentiment.get("sentiment_label"),
            "earnings_near": ticker_sentiment.get("earnings_near", False),
            "candle_pattern": candle_pattern,
            "override_reason": override_reason,
        }

        log_note = f"regime={regime}(ADX={adx_val}) active={sorted(regime_active)}"
        if candle_pattern:
            log_note += f" candle={candle_pattern}"
        if override_reason:
            log_note += f" blocked={override_reason}"
        log_step("generate_signals", signal, f"{ticker} | {log_note}")

    out_path = f".tmp/signals_{datetime.now().strftime('%Y-%m-%d')}.json"
    os.makedirs(".tmp", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    buys  = sum(1 for v in result.values() if v["signal"] == "BUY")
    sells = sum(1 for v in result.values() if v["signal"] == "SELL")
    log_step("generate_signals", "OK", f"BUY={buys} SELL={sells} HOLD={len(result)-buys-sells} -> {out_path}")
    return result

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    with open(f".tmp/bars_{today}.json") as f:
        bars = json.load(f)
    with open(f".tmp/sentiment_{today}.json") as f:
        sentiment = json.load(f)
    generate_signals(bars, sentiment)
