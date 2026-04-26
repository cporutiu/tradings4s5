import sys, os, statistics, importlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from execution.compute_indicators import add_all_indicators, to_df
from execution.candlestick_patterns import bullish_confirmation
from execution.regime_detector import detect_regime, active_strategies_for_regime
from execution.constants import STRATEGY_MODULE_MAP

STOP_LOSS_PCT   = 0.02
POSITION_PCT    = 0.05
MIN_BARS_WARMUP = 210
MAX_HOLD_BARS   = 10

def _load(sid):
    return importlib.import_module(STRATEGY_MODULE_MAP[sid])

def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    std = statistics.stdev(daily_returns)
    if std == 0:
        return 0.0
    return round((sum(daily_returns) / len(daily_returns) / std) * (252 ** 0.5), 3)

def _max_drawdown(equity_curve: list[float]) -> float:
    peak, max_dd = equity_curve[0], 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)

def _metrics(trades, equity_curve, daily_returns, initial_capital, strategy_id):
    final_equity = equity_curve[-1]
    total_return = (final_equity - initial_capital) / initial_capital
    trading_days = len(equity_curve) - 1
    ann_return = ((1 + total_return) ** (252 / max(trading_days, 1))) - 1
    win_rate = len([t for t in trades if t["pnl"] > 0]) / len(trades) if trades else 0.0
    return {
        "strategy": strategy_id,
        "total_return_pct": round(total_return * 100, 2),
        "ann_return_pct": round(ann_return * 100, 2),
        "sharpe": _sharpe(daily_returns),
        "max_drawdown_pct": round(_max_drawdown(equity_curve) * 100, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "trade_count": len(trades),
        "total_pnl": round(sum(t["pnl"] for t in trades), 2),
        "final_equity": round(final_equity, 2),
    }

def _simulate(bars, signal_fn, strategy_id, initial_capital=100_000.0):
    """
    Core simulation loop shared by single-strategy and ensemble backtests.
    signal_fn(window) -> "BUY" | "SELL" | "HOLD"
    """
    capital = initial_capital
    position = None
    trades, equity_curve, daily_returns = [], [capital], []

    for i in range(MIN_BARS_WARMUP, len(bars)):
        window = bars[:i + 1]
        today  = bars[i]
        price  = today["close"]

        if position and today["low"] <= position["stop_price"]:
            exit_price = position["stop_price"]
            capital += exit_price * position["shares"]
            trades.append({"entry_date": position["entry_date"], "exit_date": today["date"],
                           "entry": position["entry_price"], "exit": exit_price,
                           "shares": position["shares"],
                           "pnl": round((exit_price - position["entry_price"]) * position["shares"], 2),
                           "exit_reason": "stop_loss"})
            position = None

        if position and position["bars_held"] >= MAX_HOLD_BARS:
            capital += price * position["shares"]
            trades.append({"entry_date": position["entry_date"], "exit_date": today["date"],
                           "entry": position["entry_price"], "exit": price,
                           "shares": position["shares"],
                           "pnl": round((price - position["entry_price"]) * position["shares"], 2),
                           "exit_reason": "time_stop"})
            position = None

        signal = signal_fn(window)

        if signal == "BUY" and position is None:
            shares = int((capital * POSITION_PCT) / price)
            if shares >= 1:
                capital -= shares * price
                position = {"shares": shares, "entry_price": price,
                            "stop_price": round(price * (1 - STOP_LOSS_PCT), 4),
                            "entry_date": today["date"], "bars_held": 0}

        elif signal == "SELL" and position is not None:
            capital += price * position["shares"]
            trades.append({"entry_date": position["entry_date"], "exit_date": today["date"],
                           "entry": position["entry_price"], "exit": price,
                           "shares": position["shares"],
                           "pnl": round((price - position["entry_price"]) * position["shares"], 2),
                           "exit_reason": "signal"})
            position = None

        if position:
            position["bars_held"] += 1
        mtm = capital + (position["shares"] * price if position else 0)
        daily_returns.append((mtm - equity_curve[-1]) / equity_curve[-1])
        equity_curve.append(mtm)

    if position:
        last_price = bars[-1]["close"]
        capital += last_price * position["shares"]
        trades.append({"entry_date": position["entry_date"], "exit_date": bars[-1]["date"],
                       "entry": position["entry_price"], "exit": last_price,
                       "shares": position["shares"],
                       "pnl": round((last_price - position["entry_price"]) * position["shares"], 2),
                       "exit_reason": "end_of_data"})
        equity_curve[-1] = capital

    return _metrics(trades, equity_curve, daily_returns, initial_capital, strategy_id)

def _candlestick_gated(signal_fn):
    def gated(window):
        signal = signal_fn(window)
        if signal == "BUY":
            confirmed, _ = bullish_confirmation(window)
            return "BUY" if confirmed else "HOLD"
        return signal
    return gated

def backtest_single(bars, strategy_id, initial_capital=100_000.0):
    mod = _load(strategy_id)
    return _simulate(bars, _candlestick_gated(mod.run), strategy_id, initial_capital)

def backtest_ensemble(bars, strategy_ids, initial_capital=100_000.0):
    from execution.generate_signals import regime_weighted_vote
    mods = {sid: _load(sid) for sid in strategy_ids}

    def ensemble_signal(window):
        regime, _ = detect_regime(window)
        regime_active = active_strategies_for_regime(regime, strategy_ids)
        votes = {}
        for sid, mod in mods.items():
            try:
                votes[sid] = mod.run(window)
            except Exception:
                votes[sid] = "HOLD"
        signal = regime_weighted_vote(votes, regime_active)
        if signal == "BUY":
            confirmed, _ = bullish_confirmation(window)
            return "BUY" if confirmed else "HOLD"
        return signal

    return _simulate(bars, ensemble_signal, "ensemble", initial_capital)
