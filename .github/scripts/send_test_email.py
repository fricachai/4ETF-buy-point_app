from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage


RECIPIENT_EMAIL = "fricachai@gmail.com"


def main() -> None:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("ALERT_FROM_EMAIL") or username

    if not all([host, username, password, sender]):
        raise RuntimeError(
            "Missing SMTP configuration. Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, ALERT_FROM_EMAIL."
        )

    now_text = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    message = EmailMessage()
    message["Subject"] = "4檔ETF測試信"
    message["From"] = sender
    message["To"] = RECIPIENT_EMAIL
    message.set_content(
        "這是一封測試信。\n\n"
        f"收件人：{RECIPIENT_EMAIL}\n"
        f"寄件人：{sender}\n"
        f"發送時間：{now_text}\n\n"
        "如果你收到這封信，代表 GitHub Actions 的 SMTP 設定可正常寄送。"
    )

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)

    print(f"Test email sent to {RECIPIENT_EMAIL}")


if __name__ == "__main__":
    main()
