"""
run_threshold_sweep.py

Sweeps entry/exit thresholds for S4 (Golden Cross) and S5 (RSI Dip Uptrend)
across 5 years of history.

Key design: indicators are precomputed ONCE per ticker (O(n) not O(n²)),
so the full grid runs in seconds rather than 45+ minutes.

Goal: find the Pareto frontier — more entries without unjustified risk increase.
"""
import sys, os, json, statistics
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import duckdb
from datetime import datetime
from dotenv import load_dotenv
from execution.compute_indicators import add_all_indicators, to_df
from execution.init_db import DB_PATH

load_dotenv()

TICKERS         = os.getenv("WATCHLIST", "SPY,QQQ,GLD,SLV,XLE,XLF,XLK,XLV,XLU,XLI,IWM,HYG,EEM,SOXX").split(",")
MIN_BARS_WARMUP = 210
STOP_LOSS_PCT   = 0.02
POSITION_PCT    = 0.05
MAX_HOLD_BARS   = 10


# ── Fast signal functions (accept precomputed df + row index) ────────────────

def s4_signal(df, i, variant="crossover"):
    """
    All variants share the same SELL condition (EMA crossed down or macro bear).
    Entry conditions differ by variant:

      crossover    — exact EMA9/21 crossover today (baseline, ~1-2 trades/yr/ticker)
      ema21_touch  — price dips below EMA21 and closes back above while EMA9 > EMA21
                     (pullback to trend support, ~5-10 trades/yr/ticker)
      ema9_touch   — shallower: price bounces off EMA9 while in macro bull
                     (more frequent entry, ~10-20 trades/yr/ticker)
      sma50_bounce — deeper pullback: price bounces off SMA50 in macro bull
                     (medium frequency, catches bigger dips)
      recent_cross_3d — same as crossover but allows entry up to 3 bars after
                         (widens the crossover entry window)
    """
    if i < 2:
        return "HOLD"
    prev, curr = df.iloc[i - 1], df.iloc[i]
    if any(v != v for v in [curr["ema9"], curr["ema21"], curr["sma50"], curr["sma200"]]):
        return "HOLD"

    macro_bull       = curr["sma50"] > curr["sma200"]
    ema_above        = curr["ema9"] > curr["ema21"]
    ema_crossed_up   = prev["ema9"] <= prev["ema21"] and curr["ema9"] > curr["ema21"]
    ema_crossed_down = prev["ema9"] >= prev["ema21"] and curr["ema9"] < curr["ema21"]

    # Shared SELL: macro bear or EMA9 crosses below EMA21
    if not macro_bull or ema_crossed_down:
        return "SELL"

    if variant == "crossover":
        return "BUY" if ema_crossed_up else "HOLD"

    elif variant == "ema21_touch":
        bounced = prev["close"] < prev["ema21"] and curr["close"] > curr["ema21"]
        return "BUY" if ema_above and bounced else "HOLD"

    elif variant == "ema9_touch":
        bounced = prev["close"] < prev["ema9"] and curr["close"] > curr["ema9"]
        return "BUY" if ema_above and bounced else "HOLD"

    elif variant == "sma50_bounce":
        bounced = prev["close"] < prev["sma50"] and curr["close"] > curr["sma50"]
        return "BUY" if bounced else "HOLD"

    elif variant == "recent_cross_3d":
        # Allow entry on the crossover day OR within the next 2 bars
        if ema_crossed_up:
            return "BUY"
        for lookback in range(1, 3):
            if i - lookback - 1 < 0:
                break
            p = df.iloc[i - lookback - 1]
            n = df.iloc[i - lookback]
            if p["ema9"] <= p["ema21"] and n["ema9"] > n["ema21"]:
                return "BUY"
        return "HOLD"

    return "HOLD"


def s5_signal(df, i, rsi_entry=38, rsi_exit=60):
    """
    Parametric S5: RSI dip in uptrend.
      rsi_entry — oversold threshold (BUY when RSI < this AND turning up)
      rsi_exit  — recovery threshold (SELL when RSI > this)
    """
    if i < 1:
        return "HOLD"
    prev, curr = df.iloc[i - 1], df.iloc[i]
    if curr["rsi14"] != curr["rsi14"] or curr["sma200"] != curr["sma200"]:
        return "HOLD"

    in_uptrend     = curr["close"] > curr["sma200"]
    rsi_oversold   = curr["rsi14"] < rsi_entry
    rsi_turning_up = curr["rsi14"] > prev["rsi14"]
    rsi_recovered  = curr["rsi14"] > rsi_exit

    if in_uptrend and rsi_oversold and rsi_turning_up:
        return "BUY"
    if rsi_recovered:
        return "SELL"
    return "HOLD"


# ── Simulation (precomputed df path) ─────────────────────────────────────────

def _sharpe(daily_returns):
    if len(daily_returns) < 2:
        return 0.0
    std = statistics.stdev(daily_returns)
    return 0.0 if std == 0 else round((sum(daily_returns) / len(daily_returns) / std) * (252 ** 0.5), 3)

def _max_dd(equity_curve):
    peak, max_d = equity_curve[0], 0.0
    for v in equity_curve:
        peak = max(peak, v)
        max_d = max(max_d, (peak - v) / peak)
    return round(max_d * 100, 2)

def simulate(df, bars, signal_fn, initial_capital=100_000.0):
    capital = initial_capital
    position = None
    trades, equity_curve, daily_returns = [], [capital], []

    for i in range(MIN_BARS_WARMUP, len(bars)):
        today = bars[i]
        price = today["close"]

        if position and today["low"] <= position["stop_price"]:
            exit_p = position["stop_price"]
            capital += exit_p * position["shares"]
            trades.append({"pnl": round((exit_p - position["entry_price"]) * position["shares"], 2)})
            position = None

        if position and position["bars_held"] >= MAX_HOLD_BARS:
            capital += price * position["shares"]
            trades.append({"pnl": round((price - position["entry_price"]) * position["shares"], 2)})
            position = None

        signal = signal_fn(df, i)

        if signal == "BUY" and position is None:
            shares = int((capital * POSITION_PCT) / price)
            if shares >= 1:
                capital -= shares * price
                position = {"shares": shares, "entry_price": price,
                            "stop_price": round(price * (1 - STOP_LOSS_PCT), 4),
                            "bars_held": 0}

        elif signal == "SELL" and position is not None:
            capital += price * position["shares"]
            trades.append({"pnl": round((price - position["entry_price"]) * position["shares"], 2)})
            position = None

        if position:
            position["bars_held"] += 1
        mtm = capital + (position["shares"] * price if position else 0)
        daily_returns.append((mtm - equity_curve[-1]) / equity_curve[-1])
        equity_curve.append(mtm)

    if position:
        last_price = bars[-1]["close"]
        capital += last_price * position["shares"]
        trades.append({"pnl": round((last_price - position["entry_price"]) * position["shares"], 2)})
        equity_curve[-1] = capital

    final_equity = equity_curve[-1]
    total_return = (final_equity - initial_capital) / initial_capital
    win_rate = len([t for t in trades if t["pnl"] > 0]) / len(trades) if trades else 0.0

    return {
        "trade_count": len(trades),
        "total_return_pct": round(total_return * 100, 2),
        "sharpe": _sharpe(daily_returns),
        "max_dd_pct": _max_dd(equity_curve),
        "win_rate_pct": round(win_rate * 100, 1),
    }

def aggregate(results):
    n = len(results)
    if n == 0:
        return {}
    return {
        "total_trades":          sum(r["trade_count"] for r in results),
        "avg_trades_per_ticker": round(sum(r["trade_count"] for r in results) / n, 1),
        "avg_return_pct":        round(sum(r["total_return_pct"] for r in results) / n, 2),
        "avg_sharpe":            round(sum(r["sharpe"] for r in results) / n, 3),
        "avg_max_dd_pct":        round(sum(r["max_dd_pct"] for r in results) / n, 2),
        "avg_win_rate_pct":      round(sum(r["win_rate_pct"] for r in results) / n, 1),
    }


# ── Data loading ──────────────────────────────────────────────────────────────

def load_bars():
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute("""
        SELECT ticker, date, open, high, low, close, volume
        FROM bars ORDER BY ticker, date ASC
    """).fetchall()
    con.close()
    bars = {}
    for r in rows:
        t = r[0]
        bars.setdefault(t, []).append(
            {"date": str(r[1]), "open": r[2], "high": r[3],
             "low": r[4], "close": r[5], "volume": r[6]}
        )
    return bars


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_table(rows, title):
    H = (f"{'Variant':<35} {'Trades':>7} {'Tr/Tkr':>7} {'AvgRet%':>8} "
         f"{'Sharpe':>8} {'MaxDD%':>8} {'WinRate%':>9}")
    SEP = "=" * len(H)
    print(f"\n{SEP}\n{title}\n{SEP}")
    print(H)
    print("-" * len(H))
    for r in rows:
        flag = "  <<" if "[BASELINE]" in r["name"] else ""
        print(f"{r['name']:<35} {r['total_trades']:>7} {r['avg_trades_per_ticker']:>7.1f} "
              f"{r['avg_return_pct']:>8.2f} {r['avg_sharpe']:>8.3f} "
              f"{r['avg_max_dd_pct']:>8.2f} {r['avg_win_rate_pct']:>9.1f}{flag}")
    print(SEP)


def pareto(variants, baseline, label):
    print(f"\n--- {label} Pareto: more trades, Sharpe >= baseline-0.10, MaxDD <= baseline+1.0% ---")
    for r in variants:
        if "[BASELINE]" in r["name"]:
            continue
        more  = r["total_trades"] > baseline["total_trades"]
        ok_sh = r["avg_sharpe"]   >= baseline["avg_sharpe"]   - 0.10
        ok_dd = r["avg_max_dd_pct"] <= baseline["avg_max_dd_pct"] + 1.0
        dt = r["total_trades"]     - baseline["total_trades"]
        ds = r["avg_sharpe"]       - baseline["avg_sharpe"]
        dd = r["avg_max_dd_pct"]   - baseline["avg_max_dd_pct"]
        if more and ok_sh and ok_dd:
            print(f"  PASS  {r['name']:<35}  +{dt} trades | Sharpe {ds:+.3f} | DD {dd:+.2f}%")
        else:
            why = []
            if not more:  why.append(f"trades {r['total_trades']} vs baseline {baseline['total_trades']}")
            if not ok_sh: why.append(f"Sharpe {r['avg_sharpe']:.3f} vs baseline {baseline['avg_sharpe']:.3f}")
            if not ok_dd: why.append(f"DD {r['avg_max_dd_pct']:.2f}% vs baseline {baseline['avg_max_dd_pct']:.2f}%")
            print(f"  FAIL  {r['name']:<35}  ({', '.join(why)})")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_sweep():
    print(f"[threshold_sweep] START {datetime.now().strftime('%H:%M:%S')}")
    print(f"[threshold_sweep] Loading bars from {DB_PATH}...")
    all_bars = load_bars()
    tickers = [t for t in TICKERS if len(all_bars.get(t, [])) >= 220]
    print(f"[threshold_sweep] {len(tickers)} tickers: {', '.join(tickers)}")

    print("[threshold_sweep] Precomputing indicators (once per ticker)...", end=" ", flush=True)
    all_dfs = {t: add_all_indicators(to_df(all_bars[t])) for t in tickers}
    print("done.\n")

    # ── S4 variants ───────────────────────────────────────────────────────────
    s4_defs = [
        ("s4_crossover [BASELINE]",  lambda df, i: s4_signal(df, i, "crossover")),
        ("s4_ema21_touch",            lambda df, i: s4_signal(df, i, "ema21_touch")),
        ("s4_ema9_touch",             lambda df, i: s4_signal(df, i, "ema9_touch")),
        ("s4_sma50_bounce",           lambda df, i: s4_signal(df, i, "sma50_bounce")),
        ("s4_recent_cross_3d",        lambda df, i: s4_signal(df, i, "recent_cross_3d")),
    ]

    # ── S5 variants ───────────────────────────────────────────────────────────
    def mk(e, x):
        return lambda df, i: s5_signal(df, i, e, x)

    s5_defs = [
        ("s5_rsi38_exit60 [BASELINE]", mk(38, 60)),
        ("s5_rsi42_exit60",            mk(42, 60)),
        ("s5_rsi45_exit60",            mk(45, 60)),
        ("s5_rsi48_exit60",            mk(48, 60)),
        ("s5_rsi50_exit60",            mk(50, 60)),
        ("s5_rsi42_exit55",            mk(42, 55)),
        ("s5_rsi45_exit55",            mk(45, 55)),
        ("s5_rsi45_exit65",            mk(45, 65)),
        ("s5_rsi50_exit55",            mk(50, 55)),
    ]

    def run_variants(defs, label):
        rows = []
        for name, fn in defs:
            results = [simulate(all_dfs[t], all_bars[t], fn) for t in tickers]
            agg = aggregate(results)
            rows.append({"name": name, **agg})
            print(f"  {label}  {name:<35}  trades={agg['total_trades']:>4}  "
                  f"sharpe={agg['avg_sharpe']:+.3f}  dd={agg['avg_max_dd_pct']:.2f}%")
        return rows

    s4_rows = run_variants(s4_defs, "S4")
    s5_rows = run_variants(s5_defs, "S5")

    print_table(s4_rows, "S4 (Golden Cross) ENTRY VARIANTS  — 5yr backtest, 14 tickers")
    print_table(s5_rows, "S5 (RSI Dip Uptrend) THRESHOLD VARIANTS  — 5yr backtest, 14 tickers")

    baseline_s4 = next(r for r in s4_rows if "[BASELINE]" in r["name"])
    baseline_s5 = next(r for r in s5_rows if "[BASELINE]" in r["name"])
    pareto(s4_rows, baseline_s4, "S4")
    pareto(s5_rows, baseline_s5, "S5")

    out_path = f".tmp/threshold_sweep_{datetime.now().strftime('%Y-%m-%d')}.json"
    os.makedirs(".tmp", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "run_date": datetime.now().isoformat(),
            "tickers": tickers,
            "backtest_params": {
                "stop_loss_pct": STOP_LOSS_PCT,
                "position_pct": POSITION_PCT,
                "max_hold_bars": MAX_HOLD_BARS,
                "min_bars_warmup": MIN_BARS_WARMUP,
            },
            "s4_variants": s4_rows,
            "s5_variants": s5_rows,
            "baseline_s4": baseline_s4,
            "baseline_s5": baseline_s5,
        }, f, indent=2)
    print(f"\n[threshold_sweep] Results saved -> {out_path}")
    print(f"[threshold_sweep] DONE {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    run_sweep()
