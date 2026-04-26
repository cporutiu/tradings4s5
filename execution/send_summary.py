import os, sys, json, smtplib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from execution.compute_indicators import add_all_indicators, to_df
from execution.monitoring import log_step, log_warn

load_dotenv()

STRATEGY_NAMES = {
    "s1": "EMA Crossover + RSI",
    "s2": "MACD + Volume",
    "s3": "Bollinger Bands Reversion",
    "s4": "Golden/Death Cross",
    "s5": "RSI Dip in Uptrend",
}

def explain_signal(ticker: str, vote: str, bars: list, strategy_id: str) -> str:
    try:
        df = add_all_indicators(to_df(bars))
        r = df.iloc[-1]
        p = df.iloc[-2]

        if strategy_id == "s1":
            return (f"9 EMA ({r.ema9:.2f}) {'crossed above' if vote == 'BUY' else 'crossed below' if vote == 'SELL' else 'vs'} "
                    f"21 EMA ({r.ema21:.2f}) | RSI={r.rsi14:.1f}")
        elif strategy_id == "s2":
            return (f"MACD ({r.macd_line:.3f}) vs Signal ({r.macd_signal:.3f}) | "
                    f"Volume {r.volume:,.0f} vs 20d avg {r.vol_sma20:,.0f}")
        elif strategy_id == "s3":
            return (f"Close {r.close:.2f} | BB Upper={r.bb_upper:.2f} Lower={r.bb_lower:.2f} | RSI={r.rsi14:.1f}")
        elif strategy_id == "s4":
            sma200 = f"{r.sma200:.2f}" if r.sma200 == r.sma200 else "N/A"
            return f"50 SMA={r.sma50:.2f} | 200 SMA={sma200}"
        elif strategy_id == "s5":
            sma200 = f"{r.sma200:.2f}" if r.sma200 == r.sma200 else "N/A"
            return f"RSI={r.rsi14:.1f} | Close={r.close:.2f} vs 200 SMA={sma200}"
    except Exception:
        return "indicator data unavailable"
    return ""

def build_html(signals: dict, positions: dict, bars: dict, sentiment: dict) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    portfolio_value = positions.get("portfolio_value", 0)
    peak = positions.get("peak", 0)
    drawdown = positions.get("drawdown", 0)
    open_positions = positions.get("positions", [])

    signal_colors = {"BUY": "#2ecc71", "SELL": "#e74c3c", "HOLD": "#95a5a6"}

    rows = ""
    for ticker, data in signals.items():
        signal = data["signal"]
        votes = data.get("strategy_votes", {})
        sent = data.get("sentiment_label", "NEUTRAL")
        earnings = data.get("earnings_near", False)
        raw = data.get("raw_signal", signal)

        vote_rows = ""
        for sid, vote in votes.items():
            name = STRATEGY_NAMES.get(sid, sid)
            explanation = explain_signal(ticker, vote, bars.get(ticker, []), sid)
            vote_color = signal_colors.get(vote, "#95a5a6")
            vote_rows += f"""
                <tr>
                    <td style="padding:4px 8px;color:#666;">{name}</td>
                    <td style="padding:4px 8px;font-weight:bold;color:{vote_color};">{vote}</td>
                    <td style="padding:4px 8px;color:#444;font-size:12px;">{explanation}</td>
                </tr>"""

        override_note = ""
        override_reason = data.get("override_reason", "")
        candle_pattern = data.get("candle_pattern", "")
        if raw != signal and override_reason:
            override_note = f'<div style="color:#e67e22;font-size:12px;margin-top:4px;">&#9888; Downgraded from {raw} to {signal}: {override_reason}</div>'
        if candle_pattern:
            override_note += f'<div style="color:#2ecc71;font-size:12px;margin-top:2px;">&#10003; Candle confirmed: {candle_pattern}</div>'

        earnings_badge = ' <span style="background:#f39c12;color:white;padding:1px 6px;border-radius:3px;font-size:11px;">EARNINGS SOON</span>' if earnings else ""
        sent_color = {"POSITIVE": "#2ecc71", "NEGATIVE": "#e74c3c", "NEUTRAL": "#95a5a6"}.get(sent, "#95a5a6")
        regime = data.get("regime", "TRANSITION")
        adx = data.get("adx", 0)
        regime_color = {"TRENDING": "#3498db", "RANGING": "#9b59b6", "TRANSITION": "#95a5a6"}.get(regime, "#95a5a6")
        active_strats = ", ".join(data.get("regime_active_strategies", [])).upper()

        rows += f"""
        <tr>
            <td style="padding:12px 8px;border-top:1px solid #eee;">
                <strong style="font-size:16px;">{ticker}</strong>{earnings_badge}
                <div style="font-size:12px;color:{sent_color};margin-top:2px;">Sentiment: {sent}</div>
                <div style="font-size:12px;color:{regime_color};margin-top:2px;">Regime: {regime} (ADX={adx}) | Active: {active_strats}</div>
            </td>
            <td style="padding:12px 8px;border-top:1px solid #eee;text-align:center;">
                <span style="background:{signal_colors.get(signal,'#ccc')};color:white;padding:4px 12px;border-radius:4px;font-weight:bold;">{signal}</span>
                {override_note}
            </td>
            <td style="padding:12px 8px;border-top:1px solid #eee;">
                <table style="font-size:13px;">{vote_rows}</table>
            </td>
        </tr>"""

    positions_html = ""
    if open_positions:
        for p in open_positions:
            pnl_color = "#2ecc71" if p["pnl"] >= 0 else "#e74c3c"
            flags = ""
            if p.get("near_stop"):
                flags += ' <span style="background:#e74c3c;color:white;padding:1px 5px;border-radius:3px;font-size:11px;">NEAR STOP</span>'
            if p.get("earnings_near"):
                flags += ' <span style="background:#f39c12;color:white;padding:1px 5px;border-radius:3px;font-size:11px;">EARNINGS</span>'
            positions_html += f"""
            <tr>
                <td style="padding:6px 8px;">{p['ticker']}{flags}</td>
                <td style="padding:6px 8px;">{p['qty']:.0f} shares</td>
                <td style="padding:6px 8px;">Entry: ${p['entry']:.2f}</td>
                <td style="padding:6px 8px;">Current: ${p['current']:.2f}</td>
                <td style="padding:6px 8px;color:{pnl_color};font-weight:bold;">{'+' if p['pnl'] >= 0 else ''}${p['pnl']:.2f} ({p['pnl_pct']*100:+.1f}%)</td>
            </tr>"""
    else:
        positions_html = '<tr><td colspan="5" style="padding:8px;color:#999;">No open positions</td></tr>'

    drawdown_color = "#e74c3c" if drawdown > 0.05 else "#2ecc71"

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#333;">
        <h2 style="border-bottom:2px solid #2c3e50;padding-bottom:8px;">
            Trading Bot — Daily Summary <span style="font-size:14px;color:#666;">{today}</span>
        </h2>

        <table style="width:100%;background:#f8f9fa;border-radius:6px;padding:12px;margin-bottom:20px;">
            <tr>
                <td><strong>Portfolio Value</strong><br><span style="font-size:20px;">${portfolio_value:,.2f}</span></td>
                <td><strong>Peak Value</strong><br><span style="font-size:20px;">${peak:,.2f}</span></td>
                <td><strong>Drawdown</strong><br><span style="font-size:20px;color:{drawdown_color};">{drawdown*100:.1f}%</span></td>
                <td><strong>Open Positions</strong><br><span style="font-size:20px;">{len(open_positions)}/6</span></td>
            </tr>
        </table>

        <h3>Open Positions</h3>
        <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
            {positions_html}
        </table>

        <h3>Today's Signals</h3>
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:#2c3e50;color:white;">
                    <th style="padding:10px 8px;text-align:left;width:15%;">Ticker</th>
                    <th style="padding:10px 8px;text-align:center;width:12%;">Signal</th>
                    <th style="padding:10px 8px;text-align:left;">Strategy Breakdown</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>

        <p style="color:#999;font-size:11px;margin-top:24px;border-top:1px solid #eee;padding-top:8px;">
            TradingBot — Paper Account | Risk: 5% max position, 2% stop-loss, 6 positions max
        </p>
    </body></html>"""

def send_summary(signals: dict, positions: dict, bars: dict, sentiment: dict):
    gmail = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    recipient = os.getenv("SUMMARY_RECIPIENT", gmail)

    if not gmail or not app_password:
        log_warn("send_summary", "GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in .env — skipping email")
        return

    buys = sum(1 for v in signals.values() if v["signal"] == "BUY")
    sells = sum(1 for v in signals.values() if v["signal"] == "SELL")
    subject = f"TradingBot {datetime.now().strftime('%b %d')} | BUY={buys} SELL={sells} HOLD={len(signals)-buys-sells}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail
    msg["To"] = recipient
    msg.attach(MIMEText(build_html(signals, positions, bars, sentiment), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail, app_password)
            server.sendmail(gmail, recipient, msg.as_string())
        log_step("send_summary", "OK", f"Email sent to {recipient}")
    except Exception as e:
        log_warn("send_summary", f"Email failed: {e}")

if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    with open(f".tmp/signals_{today}.json") as f:
        signals = json.load(f)
    with open(f".tmp/positions_{today}.json") as f:
        positions = json.load(f)
    with open(f".tmp/bars_{today}.json") as f:
        bars = json.load(f)
    with open(f".tmp/sentiment_{today}.json") as f:
        sentiment = json.load(f)
    send_summary(signals, positions, bars, sentiment)
