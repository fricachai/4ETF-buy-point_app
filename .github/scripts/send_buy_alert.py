from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


RECIPIENT_EMAIL = "fricachai@gmail.com"
BUY_REMINDER_LOOKBACK = 10
TRACKED_ETFS = {
    "0050": {
        "name": "元大台灣50",
        "path": Path("data/0050.json"),
        "min_drop": 5.0,
        "max_drop": 7.0,
        "add_on_drop": 7.0,
    },
    "0056": {
        "name": "元大高股息",
        "path": Path("data/0056.json"),
        "min_drop": 6.0,
        "max_drop": 8.0,
        "add_on_drop": 8.0,
    },
    "00878": {
        "name": "國泰永續高股息",
        "path": Path("data/00878.json"),
        "min_drop": 5.0,
        "max_drop": 5.0,
        "add_on_drop": 5.0,
    },
    "006208": {
        "name": "富邦台50",
        "path": Path("data/006208.json"),
        "min_drop": 5.0,
        "max_drop": 7.0,
        "add_on_drop": 7.0,
    },
}


def load_candles(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def format_rule_text(min_drop: float, max_drop: float, add_on_drop: float) -> str:
    if min_drop == max_drop:
        return f"10個交易日收盤價跌幅 -{min_drop:.0f}% ( -{add_on_drop:.0f}% 時加碼 報酬率最高)"
    return (
        f"10個交易日收盤價跌幅 -{min_drop:.0f}% ~ -{max_drop:.0f}% "
        f"( -{add_on_drop:.0f}% 時加碼 報酬率最高)"
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
                f"{code} {config['name']} | 日期 {latest_candle['date'][:10]} | "
                f"買點成立 | 目前跌幅 {drop_pct:.2f}% | "
                f"基準收盤 {drawdown['base_close']:.2f} ({base_candle['date'][:10]}) | "
                f"當日收盤 {drawdown['current_close']:.2f} | {rule_text}"
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

    message = EmailMessage()
    message["Subject"] = "4檔ETF買點提醒"
    message["From"] = sender
    message["To"] = RECIPIENT_EMAIL
    message.set_content(
        "下列 ETF 在最新交易日出現買點提醒：\n\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\n\n此信件由 GitHub Actions 自動發送。"
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
