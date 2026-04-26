import os, json
from datetime import datetime
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType

load_dotenv()

MAX_POSITION_PCT = 0.05
STOP_LOSS_PCT    = 0.02
MAX_POSITIONS    = 6
MAX_DRAWDOWN_PCT = 0.10
MAX_HOLD_DAYS    = 10
ENTRY_DATES_PATH = ".tmp/entry_dates.json"

def load_entry_dates() -> dict:
    os.makedirs(".tmp", exist_ok=True)
    if os.path.exists(ENTRY_DATES_PATH):
        with open(ENTRY_DATES_PATH) as f:
            return json.load(f)
    return {}

def save_entry_dates(dates: dict):
    with open(ENTRY_DATES_PATH, "w") as f:
        json.dump(dates, f, indent=2)

def get_client():
    return TradingClient(
        os.getenv("ALPACA_API_KEY"),
        os.getenv("ALPACA_SECRET_KEY"),
        paper=True
    )

def load_portfolio_peak(portfolio_value: float) -> float:
    path = ".tmp/portfolio_peak.json"
    os.makedirs(".tmp", exist_ok=True)
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
            peak = data.get("peak", portfolio_value)
    else:
        peak = portfolio_value
    if portfolio_value > peak:
        peak = portfolio_value
        with open(path, "w") as f:
            json.dump({"peak": peak, "updated": str(datetime.now())}, f)
    return peak

def execute_trades(signals: dict):
    client = get_client()
    account = client.get_account()
    portfolio_value = float(account.portfolio_value)
    buying_power = float(account.buying_power)

    peak = load_portfolio_peak(portfolio_value)
    drawdown = (peak - portfolio_value) / peak if peak > 0 else 0.0

    if drawdown >= MAX_DRAWDOWN_PCT:
        print(f"[HALT] Circuit breaker triggered — drawdown {drawdown:.1%} >= {MAX_DRAWDOWN_PCT:.0%}. No BUY orders.")

    positions = client.get_all_positions()
    held_tickers = {p.symbol for p in positions}
    open_count = len(positions)

    entry_dates = load_entry_dates()
    today_str = datetime.now().strftime("%Y-%m-%d")
    orders_log = []

    # Time-stop: sell any position held longer than MAX_HOLD_DAYS
    for pos in positions:
        ticker = pos.symbol
        entry_str = entry_dates.get(ticker)
        if entry_str:
            days_held = (datetime.now() - datetime.fromisoformat(entry_str)).days
            if days_held >= MAX_HOLD_DAYS and signals.get(ticker, {}).get("signal") != "SELL":
                try:
                    open_orders = client.get_orders(filter={"symbols": [ticker], "status": "open"})
                    for o in open_orders:
                        client.cancel_order_by_id(o.id)
                    client.submit_order(MarketOrderRequest(
                        symbol=ticker, qty=pos.qty,
                        side=OrderSide.SELL, time_in_force=TimeInForce.DAY
                    ))
                    print(f"[TIME STOP] {ticker} — held {days_held} days >= {MAX_HOLD_DAYS}")
                    orders_log.append({"ticker": ticker, "action": "TIME_STOP", "days_held": days_held})
                    entry_dates.pop(ticker, None)
                    held_tickers.discard(ticker)
                    open_count -= 1
                except Exception as e:
                    print(f"[ERROR] TIME STOP {ticker} failed: {e}")

    for ticker, data in signals.items():
        signal = data["signal"]

        if signal == "BUY":
            if drawdown >= MAX_DRAWDOWN_PCT:
                log_skip(orders_log, ticker, "CIRCUIT_BREAKER", drawdown)
                continue
            if open_count >= MAX_POSITIONS:
                log_skip(orders_log, ticker, "MAX_POSITIONS")
                continue
            if ticker in held_tickers:
                log_skip(orders_log, ticker, "ALREADY_HELD")
                continue

            latest_price = float(client.get_latest_trade(ticker).price)
            shares = int((portfolio_value * MAX_POSITION_PCT) / latest_price)
            if shares < 1:
                log_skip(orders_log, ticker, "INSUFFICIENT_BUYING_POWER")
                continue

            stop_price = round(latest_price * (1 - STOP_LOSS_PCT), 2)

            try:
                order = client.submit_order(MarketOrderRequest(
                    symbol=ticker,
                    qty=shares,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                ))
                client.submit_order(StopOrderRequest(
                    symbol=ticker,
                    qty=shares,
                    side=OrderSide.SELL,
                    stop_price=stop_price,
                    time_in_force=TimeInForce.GTC
                ))
                entry_dates[ticker] = today_str
                print(f"[BUY] {ticker} x{shares} @ ~{latest_price} | stop @ {stop_price}")
                orders_log.append({"ticker": ticker, "action": "BUY", "shares": shares,
                                   "price": latest_price, "stop": stop_price, "order_id": str(order.id)})
                open_count += 1
            except Exception as e:
                print(f"[ERROR] BUY {ticker} failed: {e}")
                orders_log.append({"ticker": ticker, "action": "BUY_FAILED", "error": str(e)})

        elif signal == "SELL":
            if ticker not in held_tickers:
                log_skip(orders_log, ticker, "NOT_HELD")
                continue
            try:
                open_orders = client.get_orders(filter={"symbols": [ticker], "status": "open"})
                for o in open_orders:
                    client.cancel_order_by_id(o.id)

                order = client.submit_order(MarketOrderRequest(
                    symbol=ticker,
                    qty=next(p.qty for p in positions if p.symbol == ticker),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                ))
                entry_dates.pop(ticker, None)
                print(f"[SELL] {ticker} full position")
                orders_log.append({"ticker": ticker, "action": "SELL", "order_id": str(order.id)})
            except Exception as e:
                print(f"[ERROR] SELL {ticker} failed: {e}")
                orders_log.append({"ticker": ticker, "action": "SELL_FAILED", "error": str(e)})

    save_entry_dates(entry_dates)

    out_path = f".tmp/orders_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(out_path, "w") as f:
        json.dump(orders_log, f, indent=2)
    print(f"[OK] Orders log -> {out_path}")

def log_skip(log, ticker, reason, extra=None):
    msg = f"[SKIP] {ticker} — {reason}" + (f" ({extra:.1%})" if extra else "")
    print(msg)
    log.append({"ticker": ticker, "action": "SKIP", "reason": reason})

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    with open(f".tmp/signals_{today}.json") as f:
        signals = json.load(f)
    execute_trades(signals)
