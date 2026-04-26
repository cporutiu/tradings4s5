"""S3: Bollinger Bands Mean Reversion — range-bound ETFs"""
from execution.compute_indicators import add_all_indicators, to_df

def run(bars: list[dict]) -> str:
    df = add_all_indicators(to_df(bars))
    if len(df) < 25 or df[["bb_upper", "bb_lower", "rsi14"]].iloc[-1].isna().any():
        return "HOLD"

    curr = df.iloc[-1]

    touched_lower = curr["close"] <= curr["bb_lower"]
    rsi_oversold = curr["rsi14"] < 35
    touched_upper = curr["close"] >= curr["bb_upper"]

    if touched_lower and rsi_oversold:
        return "BUY"
    if touched_upper:
        return "SELL"
    return "HOLD"
