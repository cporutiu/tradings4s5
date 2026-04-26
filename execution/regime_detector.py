import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution.compute_indicators import add_all_indicators, to_df

ADX_TREND_THRESHOLD = 25
ADX_RANGE_THRESHOLD = 20

REGIME_TRENDING    = "TRENDING"
REGIME_RANGING     = "RANGING"
REGIME_TRANSITION  = "TRANSITION"

# Which strategies are active in each regime
TREND_STRATEGIES   = {"s1", "s2", "s4", "s5"}
RANGE_STRATEGIES   = {"s3", "s6"}
ALL_STRATEGIES     = TREND_STRATEGIES | RANGE_STRATEGIES

def detect_regime(bars: list[dict]) -> tuple[str, float]:
    """Returns (regime, adx_value) for the latest bar."""
    try:
        df = add_all_indicators(to_df(bars))
        adx_val = df["adx14"].iloc[-1]
        if adx_val != adx_val:  # NaN check
            return REGIME_TRANSITION, 0.0
        if adx_val >= ADX_TREND_THRESHOLD:
            return REGIME_TRENDING, round(float(adx_val), 2)
        if adx_val < ADX_RANGE_THRESHOLD:
            return REGIME_RANGING, round(float(adx_val), 2)
        return REGIME_TRANSITION, round(float(adx_val), 2)
    except Exception:
        return REGIME_TRANSITION, 0.0

def active_strategies_for_regime(regime: str, all_active: list[str]) -> set[str]:
    """Returns which strategy IDs should cast real votes given the regime."""
    if regime == REGIME_TRENDING:
        return set(all_active) & TREND_STRATEGIES
    if regime == REGIME_RANGING:
        return set(all_active) & RANGE_STRATEGIES
    return set(all_active)  # TRANSITION: all vote
