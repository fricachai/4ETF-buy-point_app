from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage


DEFAULT_RECIPIENTS = [
    "fricachai@gmail.com",
    "frica@mail.ctbctech.edu.tw",
]


def get_recipient_emails() -> list[str]:
    raw = os.environ.get("ALERT_TO_EMAILS", "").strip()
    if raw:
        recipients = [item.strip() for item in raw.split(",") if item.strip()]
        if recipients:
            return recipients
    return DEFAULT_RECIPIENTS


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

    recipients = get_recipient_emails()
    now_text = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    message = EmailMessage()
    message["Subject"] = "4 ETF test email"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(
        "This is a test email from the 4 ETF buy point monitor.\n\n"
        f"Recipients: {', '.join(recipients)}\n"
        f"Sender: {sender}\n"
        f"Timestamp: {now_text}\n\n"
        "If you received this email, GitHub Actions SMTP delivery is working."
    )

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)

    print(f"Test email sent to {', '.join(recipients)}")


if __name__ == "__main__":
    main()
