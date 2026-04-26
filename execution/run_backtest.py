import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import duckdb
from datetime import datetime
from dotenv import load_dotenv
from execution.backtest_engine import backtest_single, backtest_ensemble
from execution.regime_detector import ALL_STRATEGIES as REGIME_ALL
from execution.constants import STRATEGY_NAMES
from execution.init_db import DB_PATH
from execution.monitoring import log_step, log_warn

load_dotenv()

TICKERS            = os.getenv("WATCHLIST", "SPY,QQQ,GLD,SLV,XLE,XLF,XLK").split(",")
ALL_STRATEGIES     = sorted(REGIME_ALL)
SHARPE_MIN         = 0.3   # threshold for "strong" label
MIN_TRADES_DISABLE = 10    # need at least this many total trades to trust a DISABLE verdict

def load_all_bars() -> dict:
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute("""
        SELECT ticker, date, open, high, low, close, volume
        FROM bars ORDER BY ticker, date ASC
    """).fetchall()
    con.close()
    bars = {}
    for r in rows:
        ticker = r[0]
        bars.setdefault(ticker, []).append(
            {"date": str(r[1]), "open": r[2], "high": r[3],
             "low": r[4], "close": r[5], "volume": r[6]}
        )
    return bars

def print_table(results: list[dict]):
    header = f"{'Strategy':<30} {'Return%':>8} {'Ann%':>7} {'Sharpe':>7} {'MaxDD%':>7} {'WinRate':>8} {'Trades':>7}"
    print("\n" + "=" * len(header))
    print(header)
    print("-" * len(header))
    for r in sorted(results, key=lambda x: x["sharpe"], reverse=True):
        if r["strategy"] == "ensemble":
            flag = ""
        elif r["trade_count"] < 3:
            flag = " [LOW DATA]"
        elif r["sharpe"] < SHARPE_MIN:
            flag = " [WEAK]"
        else:
            flag = ""
        print(f"{STRATEGY_NAMES.get(r['strategy'], r['strategy']):<30} "
              f"{r['total_return_pct']:>8.1f} {r['ann_return_pct']:>7.1f} "
              f"{r['sharpe']:>7.3f} {r['max_drawdown_pct']:>7.1f} "
              f"{r['win_rate_pct']:>8.1f} {r['trade_count']:>7}{flag}")
    print("=" * len(header))

def recommend_strategies(all_results: dict) -> list[str]:
    sharpes      = {sid: [] for sid in ALL_STRATEGIES}
    trade_totals = {sid: 0  for sid in ALL_STRATEGIES}

    for ticker_results in all_results.values():
        for r in ticker_results:
            if r["strategy"] in sharpes:
                sharpes[r["strategy"]].append(r["sharpe"])
                trade_totals[r["strategy"]] += r["trade_count"]

    keep = []
    print("\n--- Strategy Recommendation ---")
    for sid in ALL_STRATEGIES:
        avg    = sum(sharpes[sid]) / len(sharpes[sid]) if sharpes[sid] else 0
        n      = trade_totals[sid]
        if n < MIN_TRADES_DISABLE:
            status = f"KEEP  (only {n} total trades - need >={MIN_TRADES_DISABLE} to trust a DISABLE)"
            keep.append(sid)
        elif avg >= SHARPE_MIN:
            status = "KEEP"
            keep.append(sid)
        elif avg >= 0:
            status = "KEEP  (marginal)"
            keep.append(sid)
        else:
            status = f"DISABLE  (avg Sharpe={avg:.3f}, n={n} trades)"
        print(f"  {STRATEGY_NAMES[sid]:<30} Sharpe={avg:+.3f}  trades={n:3d}  -> {status}")

    return keep

def run_backtest():
    if not os.path.exists(DB_PATH):
        log_warn("run_backtest", "DB not found — run backfill_history.py first")
        return

    log_step("run_backtest", "START", f"Testing {len(ALL_STRATEGIES)} strategies x {len(TICKERS)} tickers")

    all_bars    = load_all_bars()
    all_results = {}
    full_summary = []

    for ticker in TICKERS:
        bars = all_bars.get(ticker, [])
        if len(bars) < 220:
            log_warn("run_backtest", f"Skipping {ticker} — insufficient bars ({len(bars)})")
            continue

        log_step("run_backtest", "INFO", f"{ticker} ({len(bars)} bars)")
        ticker_results = []

        for sid in ALL_STRATEGIES:
            result = backtest_single(bars, sid)
            result["ticker"] = ticker
            ticker_results.append(result)

        ensemble = backtest_ensemble(bars, ALL_STRATEGIES)
        ensemble["ticker"] = ticker
        ticker_results.append(ensemble)

        all_results[ticker] = ticker_results
        print(f"\n{'='*20} {ticker} {'='*20}")
        print_table(ticker_results)
        full_summary.extend(ticker_results)

    print("\n\n" + "=" * 60)
    print("CROSS-TICKER AVERAGE PERFORMANCE")
    print("=" * 60)
    for sid in ALL_STRATEGIES + ["ensemble"]:
        matching = [r for r in full_summary if r["strategy"] == sid]
        if matching:
            total_trades = sum(r["trade_count"] for r in matching)
            print(f"  {STRATEGY_NAMES[sid]:<30} "
                  f"Sharpe={sum(r['sharpe'] for r in matching)/len(matching):+.3f}  "
                  f"AnnReturn={sum(r['ann_return_pct'] for r in matching)/len(matching):.1f}%  "
                  f"WinRate={sum(r['win_rate_pct'] for r in matching)/len(matching):.1f}%  "
                  f"Trades={total_trades}")

    recommended    = recommend_strategies(all_results)
    recommended_str = ",".join(recommended)
    print(f"\n  Recommended ACTIVE_STRATEGIES={recommended_str}")

    out_path = f".tmp/backtest_results_{datetime.now().strftime('%Y-%m-%d')}.json"
    os.makedirs(".tmp", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "results": [{k: v for k, v in r.items()} for r in full_summary],
            "recommended_strategies": recommended_str,
            "run_date": datetime.now().isoformat()
        }, f, indent=2)

    log_step("run_backtest", "DONE", f"Results -> {out_path}")
    print(f"\nTo apply results, update ACTIVE_STRATEGIES in .env to: {recommended_str}")
    return recommended_str

if __name__ == "__main__":
    run_backtest()
