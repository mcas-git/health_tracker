from __future__ import annotations

import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

# Support direct execution locally and from GitHub Actions.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from health_tracker.config import setting


def main() -> None:
    required = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "REMINDER_FROM", "REMINDER_TO"]
    missing = [name for name in required if not setting(name)]
    if missing:
        raise SystemExit(f"Missing reminder settings: {', '.join(missing)}")
    message = EmailMessage()
    message["Subject"] = "A two-minute health check-in 🌿"
    message["From"] = setting("REMINDER_FROM")
    message["To"] = setting("REMINDER_TO")
    url = setting("APP_URL", "http://localhost:8501")
    message.set_content(
        f"Take two minutes to record today's food, measurements, fasting and habits.\n\n{url}\n"
    )
    host = setting("SMTP_HOST", "smtp.gmail.com")
    port = int(setting("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(setting("SMTP_USERNAME"), setting("SMTP_PASSWORD"))
        smtp.send_message(message)


if __name__ == "__main__":
    main()
