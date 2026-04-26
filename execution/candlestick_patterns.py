def detect_patterns(candle: dict, prev: dict) -> dict:
    """
    Detect bullish/bearish candlestick patterns from two consecutive daily bars.
    Returns a dict of pattern name -> bool.
    """
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    po, ph, pl, pc = prev["open"], prev["high"], prev["low"], prev["close"]

    body = abs(c - o)
    full_range = h - l if h != l else 0.0001
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    bullish_candle = c > o
    bearish_candle = c < o

    patterns = {}

    # Bullish engulfing: current bullish body fully wraps previous bearish body
    patterns["bullish_engulfing"] = (
        bullish_candle and (pc < po) and c > po and o < pc
    )

    # Hammer: bullish or neutral, lower wick >= 2x body, upper wick small, appears after decline
    patterns["hammer"] = (
        body / full_range < 0.4 and
        lower_wick >= 2 * body and
        upper_wick <= body * 0.5 and
        c < pc  # appears after a down move
    )

    # Inverted hammer: small body at bottom, long upper wick (needs follow-through, use loosely)
    patterns["inverted_hammer"] = (
        body / full_range < 0.35 and
        upper_wick >= 2 * body and
        lower_wick <= body * 0.5
    )

    # Bearish engulfing: current bearish body fully wraps previous bullish body
    patterns["bearish_engulfing"] = (
        bearish_candle and (pc > po) and o > pc and c < po
    )

    # Shooting star: bearish or neutral, upper wick >= 2x body, lower wick small
    patterns["shooting_star"] = (
        body / full_range < 0.4 and
        upper_wick >= 2 * body and
        lower_wick <= body * 0.5 and
        bearish_candle
    )

    # Doji: body is very small relative to range (indecision)
    patterns["doji"] = body / full_range < 0.1

    return patterns

def bullish_confirmation(bars: list[dict]) -> tuple[bool, str]:
    """Returns (confirmed, pattern_name) for the latest bar."""
    if len(bars) < 2:
        return False, "insufficient data"

    curr = bars[-1]
    prev = bars[-2]
    patterns = detect_patterns(curr, prev)

    bullish_patterns = ["bullish_engulfing", "hammer", "inverted_hammer"]
    for name in bullish_patterns:
        if patterns.get(name):
            return True, name

    return False, "no bullish pattern"

def bearish_confirmation(bars: list[dict]) -> tuple[bool, str]:
    """Returns (confirmed, pattern_name) for the latest bar."""
    if len(bars) < 2:
        return False, "insufficient data"

    curr = bars[-1]
    prev = bars[-2]
    patterns = detect_patterns(curr, prev)

    bearish_patterns = ["bearish_engulfing", "shooting_star"]
    for name in bearish_patterns:
        if patterns.get(name):
            return True, name

    return False, "no bearish pattern"
