import pandas as pd

def to_df(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["date"])
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

def ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()

def sma(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].rolling(window=period).mean()

def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

def macd(df: pd.DataFrame, fast=12, slow=26, signal=9):
    fast_ema = df["close"].ewm(span=fast, adjust=False).mean()
    slow_ema = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def bollinger_bands(df: pd.DataFrame, period=20, std_dev=2):
    mid = df["close"].rolling(window=period).mean()
    std = df["close"].rolling(window=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def volume_sma(df: pd.DataFrame, period=20) -> pd.Series:
    return df["volume"].rolling(window=period).mean()

def stochastic(df: pd.DataFrame, k_period=14, d_period=3):
    lowest_low = df["low"].rolling(window=k_period).min()
    highest_high = df["high"].rolling(window=k_period).max()
    denom = (highest_high - lowest_low).replace(0, float("nan"))
    k = 100 * (df["close"] - lowest_low) / denom
    d = k.rolling(window=d_period).mean()
    return k, d

def adx(df: pd.DataFrame, period=14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    # Wilder smoothing = EWM with alpha=1/period (correct, bounded 0-100)
    alpha = 1 / period
    atr = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    return dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema9"] = ema(df, 9)
    df["ema21"] = ema(df, 21)
    df["sma50"] = sma(df, 50)
    df["sma200"] = sma(df, 200)
    df["rsi14"] = rsi(df, 14)
    df["macd_line"], df["macd_signal"] = macd(df)
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(df)
    df["vol_sma20"] = volume_sma(df, 20)
    df["stoch_k"], df["stoch_d"] = stochastic(df)
    df["adx14"] = adx(df)
    return df
