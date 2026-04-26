"""S5: RSI Dip in Uptrend — aggressive calibration (week of 2026-04-28)
Enters when RSI < 50 (any sub-neutral dip) AND already turning back up,
while price is above SMA200. Exits when RSI recovers past 55.
Sweep result: rsi50/exit55 — Sharpe 0.612 vs 0.560 baseline, +326 trades,
AvgReturn 1.09% vs 0.66%. Revisit conservative (rsi45/exit55) week of 2026-05-05.
"""
from execution.compute_indicators import add_all_indicators, to_df

RSI_ENTRY = 50
RSI_EXIT  = 55

def run(bars: list[dict]) -> str:
    df = add_all_indicators(to_df(bars))
    if len(df) < 210 or df[["rsi14", "sma200"]].iloc[-1].isna().any():
        return "HOLD"

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    in_uptrend     = curr["close"] > curr["sma200"]
    rsi_dipping    = curr["rsi14"] < RSI_ENTRY
    rsi_turning_up = curr["rsi14"] > prev["rsi14"]
    rsi_recovered  = curr["rsi14"] > RSI_EXIT

    if in_uptrend and rsi_dipping and rsi_turning_up:
        return "BUY"
    if rsi_recovered:
        return "SELL"
    return "HOLD"
