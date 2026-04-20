from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


DEFAULT_RECIPIENTS = [
    "fricachai@gmail.com",
    "frica@mail.ctbctech.edu.tw",
]
BUY_REMINDER_LOOKBACK = 10
TRACKED_ETFS = {
    "0050": {
        "name": "Yuanta Taiwan 50",
        "path": Path("data/0050.json"),
        "min_drop": 5.0,
        "max_drop": 7.0,
        "add_on_drop": 7.0,
    },
    "0056": {
        "name": "Yuanta High Dividend",
        "path": Path("data/0056.json"),
        "min_drop": 6.0,
        "max_drop": 8.0,
        "add_on_drop": 8.0,
    },
    "00878": {
        "name": "Cathay Sustainable High Dividend",
        "path": Path("data/00878.json"),
        "min_drop": 4.5,
        "max_drop": 5.5,
        "add_on_drop": 5.0,
    },
    "006208": {
        "name": "Fubon Taiwan 50",
        "path": Path("data/006208.json"),
        "min_drop": 5.0,
        "max_drop": 7.0,
        "add_on_drop": 7.0,
    },
}


def get_recipient_emails() -> list[str]:
    raw = os.environ.get("ALERT_TO_EMAILS", "").strip()
    if raw:
        recipients = [item.strip() for item in raw.split(",") if item.strip()]
        if recipients:
            return recipients
    return DEFAULT_RECIPIENTS


def load_candles(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def format_rule_text(min_drop: float, max_drop: float, add_on_drop: float) -> str:
    def fmt(value: float) -> str:
        return f"{int(value)}" if float(value).is_integer() else f"{value:.1f}"

    if min_drop == max_drop:
        return f"10-day close drop -{fmt(min_drop)}% (add on at -{fmt(add_on_drop)}%)"
    return (
        f"10-day close drop -{fmt(min_drop)}% ~ -{fmt(max_drop)}% "
        f"(add on at -{fmt(add_on_drop)}%)"
    )


def calculate_drawdown_window(candles: list[dict], end_index: int, lookback: int = BUY_REMINDER_LOOKBACK) -> dict | None:
    if end_index < 0 or end_index >= len(candles):
        return None

    start_index = end_index - lookback + 1
    if start_index < 0:
        return None

    base_close = None
    base_index = -1
    for index in range(start_index, end_index + 1):
        close = float(candles[index]["close"])
        if base_close is None or close > base_close:
            base_close = close
            base_index = index

    current_close = float(candles[end_index]["close"])
    if base_close is None or base_close <= 0:
        return None

    drop_pct = ((base_close - current_close) / base_close) * 100
    return {
        "base_index": base_index,
        "base_close": base_close,
        "current_close": current_close,
        "drop_pct": drop_pct,
    }


def build_alert_lines() -> list[str]:
    lines: list[str] = []

    for code, config in TRACKED_ETFS.items():
        candles = load_candles(config["path"])
        if not candles:
            continue

        latest_index = len(candles) - 1
        drawdown = calculate_drawdown_window(candles, latest_index)
        if not drawdown:
            continue

        drop_pct = drawdown["drop_pct"]
        if not (config["min_drop"] <= drop_pct <= config["max_drop"]):
            continue

        latest_candle = candles[latest_index]
        base_candle = candles[drawdown["base_index"]]
        rule_text = format_rule_text(config["min_drop"], config["max_drop"], config["add_on_drop"])
        lines.append(
            (
                f"{code} {config['name']} | date {latest_candle['date'][:10]} | "
                f"signal triggered | current drop {drop_pct:.2f}% | "
                f"base close {drawdown['base_close']:.2f} ({base_candle['date'][:10]}) | "
                f"latest close {drawdown['current_close']:.2f} | {rule_text}"
            )
        )

    return lines


def send_email(lines: list[str]) -> None:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("ALERT_FROM_EMAIL") or username

    if not all([host, username, password, sender]):
        raise RuntimeError(
            "Missing SMTP configuration. Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, ALERT_FROM_EMAIL."
        )

    recipients = get_recipient_emails()
    message = EmailMessage()
    message["Subject"] = "4 ETF buy point alert"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(
        "The following ETFs triggered buy point alerts on the latest trading day:\n\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\n\nThis email was sent automatically by GitHub Actions."
    )

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)


def main() -> None:
    lines = build_alert_lines()
    if not lines:
        print("No ETF buy alerts today.")
        return

    send_email(lines)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
