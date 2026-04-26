"""S4: SMA50 Bounce in Macro Bull
Enters when price pulls back to SMA50 and closes back above it, while the
macro bull filter (SMA50 > SMA200) is intact. Exits on EMA9/21 death cross
or macro bear. Sweep result: Sharpe 0.460 vs 0.277 baseline, +48 trades,
WinRate 45.9% — strictly dominates the old EMA crossover variant.
"""
from execution.compute_indicators import add_all_indicators, to_df

def run(bars: list[dict]) -> str:
    df = add_all_indicators(to_df(bars))
    if len(df) < 210 or df[["ema9", "ema21", "sma50", "sma200"]].iloc[-1].isna().any():
        return "HOLD"

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    macro_bull       = curr["sma50"] > curr["sma200"]
    ema_crossed_down = prev["ema9"] >= prev["ema21"] and curr["ema9"] < curr["ema21"]
    bounced_sma50    = prev["close"] < prev["sma50"] and curr["close"] > curr["sma50"]

    if not macro_bull or ema_crossed_down:
        return "SELL"
    if bounced_sma50:
        return "BUY"
    return "HOLD"
