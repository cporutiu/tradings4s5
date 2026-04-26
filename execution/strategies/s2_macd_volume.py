"""S2: MACD + Volume Confirmation — momentum"""
import pandas as pd
from execution.compute_indicators import add_all_indicators, to_df

def run(bars: list[dict]) -> str:
    df = add_all_indicators(to_df(bars))
    if len(df) < 35 or df[["macd_line", "macd_signal", "vol_sma20"]].iloc[-1].isna().any():
        return "HOLD"

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    macd_crossed_up = prev["macd_line"] <= prev["macd_signal"] and curr["macd_line"] > curr["macd_signal"]
    macd_crossed_down = prev["macd_line"] >= prev["macd_signal"] and curr["macd_line"] < curr["macd_signal"]
    volume_above_avg = curr["volume"] > curr["vol_sma20"]

    if macd_crossed_up and volume_above_avg:
        return "BUY"
    if macd_crossed_down:
        return "SELL"
    return "HOLD"
