"""S6: Stochastic Oscillator — range trading (tight, low-volatility consolidation)"""
from execution.compute_indicators import add_all_indicators, to_df

def run(bars: list[dict]) -> str:
    df = add_all_indicators(to_df(bars))
    if len(df) < 20 or df[["stoch_k", "stoch_d"]].iloc[-1].isna().any():
        return "HOLD"

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # %K crosses above %D while both in oversold zone (<20) -> BUY
    k_crossed_up = prev["stoch_k"] <= prev["stoch_d"] and curr["stoch_k"] > curr["stoch_d"]
    oversold = curr["stoch_k"] < 20

    # %K crosses below %D while both in overbought zone (>80) -> SELL
    k_crossed_down = prev["stoch_k"] >= prev["stoch_d"] and curr["stoch_k"] < curr["stoch_d"]
    overbought = curr["stoch_k"] > 80

    if k_crossed_up and oversold:
        return "BUY"
    if k_crossed_down and overbought:
        return "SELL"
    return "HOLD"
