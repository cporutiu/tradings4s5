import os, json
from datetime import datetime
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

load_dotenv()

STOP_LOSS_PCT       = 0.02
NEAR_STOP_THRESHOLD = 0.005
MAX_HOLD_DAYS       = 10
ENTRY_DATES_PATH    = ".tmp/entry_dates.json"

def check_positions():
    client = TradingClient(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET_KEY"),
        paper=True
    )
    account = client.get_account()
    portfolio_value = float(account.portfolio_value)

    peak_path = ".tmp/portfolio_peak.json"
    os.makedirs(".tmp", exist_ok=True)
    peak = portfolio_value
    if os.path.exists(peak_path):
        with open(peak_path) as f:
            peak = json.load(f).get("peak", portfolio_value)
    if portfolio_value > peak:
        peak = portfolio_value
        with open(peak_path, "w") as f:
            json.dump({"peak": peak, "updated": str(datetime.now())}, f)

    drawdown = (peak - portfolio_value) / peak if peak > 0 else 0.0
    positions = client.get_all_positions()

    sentiment_path = f".tmp/sentiment_{datetime.now().strftime('%Y-%m-%d')}.json"
    sentiment = {}
    if os.path.exists(sentiment_path):
        with open(sentiment_path) as f:
            sentiment = json.load(f)

    entry_dates = {}
    if os.path.exists(ENTRY_DATES_PATH):
        with open(ENTRY_DATES_PATH) as f:
            entry_dates = json.load(f)

    print(f"\nPortfolio Value: ${portfolio_value:,.2f} | Peak: ${peak:,.2f} | Drawdown: {drawdown:.1%}")
    print(f"Open Positions ({len(positions)}/6):")

    snapshot = []
    for pos in positions:
        entry = float(pos.avg_entry_price)
        current = float(pos.current_price)
        qty = float(pos.qty)
        pnl = (current - entry) * qty
        pnl_pct = (current - entry) / entry

        stop_price = round(entry * (1 - STOP_LOSS_PCT), 2)
        near_stop = current <= stop_price * (1 + NEAR_STOP_THRESHOLD)
        earnings_near = sentiment.get(pos.symbol, {}).get("earnings_near", False)
        entry_str = entry_dates.get(pos.symbol)
        days_held = (datetime.now() - datetime.fromisoformat(entry_str)).days if entry_str else None
        time_stop_due = days_held is not None and days_held >= MAX_HOLD_DAYS

        flags = ""
        if near_stop:
            flags += " NEAR STOP"
        if time_stop_due:
            flags += f" TIME STOP ({days_held}d)"
        elif days_held is not None:
            flags += f" ({days_held}d)"
        if earnings_near:
            flags += " EARNINGS SOON"

        print(f"  {pos.symbol:<5} | {qty:.0f} shares | Entry: ${entry:.2f} | "
              f"Current: ${current:.2f} | P&L: {'+' if pnl >= 0 else ''}"
              f"${pnl:.2f} ({pnl_pct:+.1%}){flags}")

        snapshot.append({
            "ticker": pos.symbol, "qty": qty, "entry": entry,
            "current": current, "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 4),
            "days_held": days_held, "near_stop": near_stop,
            "time_stop_due": time_stop_due, "earnings_near": earnings_near
        })

    if not positions:
        print("  No open positions.")

    out_path = f".tmp/positions_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(out_path, "w") as f:
        json.dump({"portfolio_value": portfolio_value, "peak": peak,
                   "drawdown": round(drawdown, 4), "positions": snapshot}, f, indent=2)
    print(f"\n[OK] Positions snapshot -> {out_path}\n")
    return snapshot

if __name__ == "__main__":
    check_positions()
