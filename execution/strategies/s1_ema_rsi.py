"""S1: EMA Crossover + RSI Filter — trend following"""
import pandas as pd
from execution.compute_indicators import add_all_indicators, to_df

def run(bars: list[dict]) -> str:
    df = add_all_indicators(to_df(bars))
    if len(df) < 30 or df[["ema9", "ema21", "rsi14"]].iloc[-1].isna().any():
        return "HOLD"

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    ema_crossed_up = prev["ema9"] <= prev["ema21"] and curr["ema9"] > curr["ema21"]
    ema_crossed_down = prev["ema9"] >= prev["ema21"] and curr["ema9"] < curr["ema21"]
    rsi_not_overbought = curr["rsi14"] < 70

    if ema_crossed_up and rsi_not_overbought:
        return "BUY"
    if ema_crossed_down:
        return "SELL"
    return "HOLD"
